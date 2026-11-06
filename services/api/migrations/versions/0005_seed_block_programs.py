"""Seed block programs and the paths that run them (Iron Tempo, #64).

Inserts every seed exercise and path not in the tables yet, then each block program in
`program.json["programs"]` (program row, phases, session templates, prescriptions) unless that
program slug and version is already there. Safe on any database: running it against one seeded from the
current program.json only adds what is missing.

A block prescription is stored with its first movement as the exercise and its rounds as the sets; the
rules engine reads the full block from program.json (the DB is used for ids only).

Revision ID: 0005
Revises: 0004
"""

import json

import sqlalchemy as sa
from alembic import op

from app.config import settings

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _run(conn, sql: str, params: dict | None = None):
    return conn.execute(sa.text(sql), params or {})


def _first_exercise(pr: dict) -> str:
    return pr["block"]["movements"][0]["exercise"] if pr.get("block") else pr["exercise"]


def upgrade() -> None:
    seed = json.loads(settings.seed_path.read_text(encoding="utf-8"))
    conn = op.get_bind()

    have = {slug for (slug,) in _run(conn, "SELECT slug FROM exercises")}
    added = [e for e in seed["exercises"] if e["slug"] not in have]
    for e in added:
        _run(
            conn,
            "INSERT INTO exercises (slug, name, equipment, needs_garage_space, increment_lb, is_timed) "
            "VALUES (:slug, :name, :equipment, :ngs, :inc, :timed)",
            {
                "slug": e["slug"],
                "name": e["name"],
                "equipment": e["equipment"],
                "ngs": e["needs_garage_space"],
                "inc": e["increment_lb"],
                "timed": e["is_timed"],
            },
        )
    for e in added:
        if e["swap"]:
            _run(
                conn,
                "UPDATE exercises SET swap_exercise_id = (SELECT id FROM exercises WHERE slug = :swap) "
                "WHERE slug = :slug",
                {"swap": e["swap"], "slug": e["slug"]},
            )
    ids = {slug: i for slug, i in _run(conn, "SELECT slug, id FROM exercises")}

    paths = {slug for (slug,) in _run(conn, "SELECT slug FROM paths")}
    for pa in seed["paths"]:
        if pa["slug"] in paths:
            continue
        pid = _run(
            conn,
            "INSERT INTO paths (slug, name, tagline, build, ratio_target, colors, emphasis, "
            "conditioning_exercise_id) VALUES (:slug, :name, :tagline, :build, :ratio, "
            "CAST(:colors AS jsonb), CAST(:emphasis AS jsonb), :cond) RETURNING id",
            {
                "slug": pa["slug"],
                "name": pa["name"],
                "tagline": pa["tagline"],
                "build": pa["build"],
                "ratio": pa["ratio_target"],
                "colors": json.dumps(pa["colors"]),
                "emphasis": json.dumps(pa["emphasis"]),
                "cond": ids[pa["conditioning_exercise"]],
            },
        ).scalar_one()
        for i, t in enumerate(pa["techniques"], 1):
            _run(
                conn,
                "INSERT INTO path_techniques (path_id, exercise_id, ord, sets, rep_min, rep_max, note) "
                "VALUES (:pid, :ex, :ord, :sets, :rep_min, :rep_max, :note)",
                {
                    "pid": pid,
                    "ex": ids[t["exercise"]],
                    "ord": i,
                    "sets": t["sets"],
                    "rep_min": t["rep_min"],
                    "rep_max": t["rep_max"],
                    "note": t.get("note"),
                },
            )

    for b in seed.get("programs", []):
        exists = _run(
            conn,
            "SELECT 1 FROM programs WHERE slug = :slug AND version = :version",
            {"slug": b["slug"], "version": b["version"]},
        ).first()
        if exists:
            continue
        prog = _run(
            conn,
            "INSERT INTO programs (slug, version, name) VALUES (:slug, :version, :name) RETURNING id",
            {"slug": b["slug"], "version": b["version"], "name": b["name"]},
        ).scalar_one()
        for ph in b["phases"]:
            _run(
                conn,
                "INSERT INTO phases (program_id, ord, name, display_name_template, kind, start_week, end_week, "
                "rir_target, deload_every, calorie_mode, modifiers) VALUES (:prog, :ord, :name, :tpl, :kind, "
                ":start_week, :end_week, :rir, :deload, :calorie_mode, CAST(:modifiers AS jsonb))",
                {
                    "prog": prog,
                    "ord": ph["ord"],
                    "name": ph["name"],
                    "tpl": ph.get("display_name_template"),
                    "kind": ph["kind"],
                    "start_week": ph["start_week"],
                    "end_week": ph["end_week"],
                    "rir": ph["rir_target"],
                    "deload": ph["deload_every"],
                    "calorie_mode": ph["calorie_mode"],
                    "modifiers": json.dumps(ph["modifiers"]),
                },
            )
        for st in b["session_templates"]:
            tid = _run(
                conn,
                "INSERT INTO session_templates (program_id, code, name, short_name, kind, day_of_week, "
                "gets_path_techniques, required_for_full_week, uses_path_conditioning) VALUES (:prog, :code, "
                ":name, :short, CAST(:kind AS session_kind), :dow, :gpt, :required, false) RETURNING id",
                {
                    "prog": prog,
                    "code": st["code"],
                    "name": st["name"],
                    "short": st["short"],
                    "kind": st["kind"],
                    "dow": st["day_of_week"],
                    "gpt": st["gets_path_techniques"],
                    "required": st["required_for_full_week"],
                },
            ).scalar_one()
            for i, pr in enumerate(st["prescriptions"], 1):
                block = pr.get("block")
                _run(
                    conn,
                    "INSERT INTO prescriptions (session_template_id, exercise_id, ord, sets, rep_min, rep_max, "
                    "rest_seconds, superset_group, is_main_lift, note) VALUES (:tid, :ex, :ord, :sets, "
                    ":rep_min, :rep_max, COALESCE(:rest, 90), :superset, :main, :note)",
                    {
                        "tid": tid,
                        "ex": ids[_first_exercise(pr)],
                        "ord": i,
                        "sets": block["rounds"] if block else pr["sets"],
                        "rep_min": 1 if block else pr["rep_min"],
                        "rep_max": 1 if block else pr["rep_max"],
                        "rest": pr.get("rest_seconds"),
                        "superset": pr.get("superset_group"),
                        "main": pr.get("is_main_lift", False),
                        "note": pr.get("note") or (block["name"] if block else None),
                    },
                )


def downgrade() -> None:
    seed = json.loads(settings.seed_path.read_text(encoding="utf-8"))
    conn = op.get_bind()
    # Remove the block programs unless something was logged on them; exercises and paths stay (they may be
    # referenced by logged sets or enrollments).
    for b in seed.get("programs", []):
        used = _run(
            conn,
            "SELECT 1 FROM enrollments e JOIN programs p ON p.id = e.program_id "
            "WHERE p.slug = :slug AND p.version = :version LIMIT 1",
            {"slug": b["slug"], "version": b["version"]},
        ).first()
        if used:
            continue
        _run(
            conn,
            "DELETE FROM prescriptions WHERE session_template_id IN (SELECT st.id FROM session_templates st "
            "JOIN programs p ON p.id = st.program_id WHERE p.slug = :slug AND p.version = :version)",
            {"slug": b["slug"], "version": b["version"]},
        )
        for table in ("session_templates", "phases"):
            _run(
                conn,
                f"DELETE FROM {table} WHERE program_id IN "
                "(SELECT id FROM programs WHERE slug = :slug AND version = :version)",
                {"slug": b["slug"], "version": b["version"]},
            )
        _run(
            conn,
            "DELETE FROM programs WHERE slug = :slug AND version = :version",
            {"slug": b["slug"], "version": b["version"]},
        )
