"""Import an export (`GET /v1/export` JSON) into a fresh account: the M4 round-trip.

Rows are re-created through the same paths the app uses (sync, Trial upserts, scans), so every award is
recomputed by the rules engine rather than copied. Client ids get new deterministic UUID5s per account,
because session and set client ids are unique server-wide; re-importing the same export is a no-op.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.models import BodyScan, Enrollment, User, UserLift, WorkoutSession
from app.rules.program import Program
from app.rules.trials import trial_awards
from app.rules.xp import Award, scan_award
from app.services.awards import award_badges, record_awards
from app.services.program import program_ids
from app.services.stats import Stats, refresh_stats, trial_results
from app.services.sync import SessionInput, SetInput, run_sync
from app.services.trials import upsert_trial_results

RESTORE_NS = uuid.UUID("0b6f7a52-9d1e-4c3a-8f1b-2e5d6c7a8b90")


def _ts(v: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(v) if v else None


def _date(v: str) -> dt.date:
    return dt.date.fromisoformat(v)


def restore_export(
    db: Session, user: User, export: dict[str, Any], program: Program
) -> tuple[list[Award], Stats]:
    if export.get("format_version") != 1:
        raise ApiError(422, "invalid_export", "unsupported export format")
    tables: dict[str, list[dict[str, Any]]] = export.get("tables") or {}
    has_runs = db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.user_id == user.id))
    if has_runs:
        raise ApiError(
            409, "account_not_empty", "import an export into a fresh account (this one already has a run)"
        )

    ids = program_ids(db)
    new_id = lambda old: uuid.uuid5(RESTORE_NS, f"{user.id}:{old}")  # noqa: E731

    # Runs, oldest first. Only one may be active; the rest keep their status.
    runs: dict[str, Enrollment] = {}
    for row in sorted(tables.get("enrollments", []), key=lambda r: r["started_on"]):
        e = Enrollment(
            id=new_id(row["id"]),
            user_id=user.id,
            program_id=ids.program_id_for(program.for_path(ids.path_slug(row["path_id"]))),
            path_id=row["path_id"],
            cycle=row.get("cycle", 1),
            started_on=_date(row["started_on"]),
            status=row["status"],
            garage_mode_default=row.get("garage_mode_default", False),
        )
        db.add(e)
        runs[row["id"]] = e
    db.flush()

    # Sessions and sets, run by run, through the sync path (awards recomputed, idempotent).
    set_rows = tables.get("set_logs", [])
    client_of_row = {r["id"]: r["client_id"] for r in set_rows}
    sets_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in set_rows:
        sets_by_session[r["workout_session_id"]].append(r)
    awards: list[Award] = []
    sessions_by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in tables.get("workout_sessions", []):
        sessions_by_run[s["enrollment_id"]].append(s)
    for old_run, sessions in sessions_by_run.items():
        e = runs.get(old_run)
        if e is None:
            continue
        inputs = [
            SessionInput(
                client_id=new_id(s["client_id"]),
                template_code=ids.template_code(s["session_template_id"]),
                week=s["week"],
                garage_mode=s["garage_mode"],
                started_at=_ts(s["started_at"]),
                completed_at=_ts(s.get("completed_at")),
            )
            for s in sessions
        ]
        set_inputs = [
            SetInput(
                client_id=new_id(r["client_id"]),
                session_client_id=new_id(s["client_id"]),
                exercise_slug=ids.exercise_slug(r["exercise_id"]),
                set_no=r["set_no"],
                weight_lb=float(r["weight_lb"]),
                logged_at=_ts(r["logged_at"]),
                reps=r.get("reps"),
                seconds=r.get("seconds"),
                rir=r.get("rir"),
                is_swap=r.get("is_swap", False),
                supersedes_client_id=new_id(client_of_row[r["supersedes_id"]])
                if r.get("supersedes_id")
                else None,
            )
            for s in sessions
            for r in sets_by_session.get(s["id"], [])
        ]
        result = run_sync(db, user, e, program, inputs, set_inputs)
        awards += result.xp_awarded
        # Keep the path each session was done on.
        for s in sessions:
            if s.get("path_id"):
                db.execute(
                    update(WorkoutSession)
                    .where(WorkoutSession.client_id == new_id(s["client_id"]))
                    .values(path_id=s["path_id"])
                )

    # Trials, per run and phase.
    trials: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    taken: dict[tuple[str, int], dt.datetime] = {}
    for t in tables.get("test_results", []):
        if not t.get("enrollment_id") or t["enrollment_id"] not in runs or t.get("phase_id") is None:
            continue
        key = (t["enrollment_id"], ids.phase_ord(t["phase_id"]))
        trials[key][t["test"]] = float(t["value"])
        taken[key] = max(taken.get(key, _ts(t["taken_at"])), _ts(t["taken_at"]))
    for (old_run, ord_), results in trials.items():
        e = runs[old_run]
        upsert_trial_results(db, user.id, e, ord_, results, taken[(old_run, ord_)])
        awards += record_awards(
            db,
            user.id,
            trial_awards(str(e.id), ord_, trial_results(db, user.id, e.id).get(ord_, {}), program),
        )

    # Tape scans (no photos are exported).
    for sc in tables.get("body_scans", []):
        sid = new_id(sc["id"])
        db.execute(
            insert(BodyScan)
            .values(
                id=sid,
                user_id=user.id,
                status=sc.get("status", "done"),
                shoulders_in=sc.get("shoulders_in"),
                waist_in=sc.get("waist_in"),
                taken_at=_ts(sc["taken_at"]),
            )
            .on_conflict_do_nothing(index_elements=[BodyScan.id])
        )
        awards += record_awards(db, user.id, [scan_award(str(sid))])

    # 1RMs (Iron Tempo), keeping when they were last tested.
    for lift in tables.get("user_lifts", []):
        db.execute(
            insert(UserLift)
            .values(
                user_id=user.id,
                exercise_id=lift["exercise_id"],
                one_rm_lb=lift["one_rm_lb"],
                updated_at=_ts(lift.get("updated_at")) or dt.datetime.now(dt.UTC),
            )
            .on_conflict_do_nothing(index_elements=[UserLift.user_id, UserLift.exercise_id])
        )

    active = next((e for e in runs.values() if e.status == "active"), None)
    _, badge_xp = award_badges(db, user.id, active, program)
    return awards + badge_xp, refresh_stats(db, user.id, program)
