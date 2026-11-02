"""Seed program content from db/seed/program.json (port of db/load_seed.py).

Revision ID: 0002
Revises: 0001
"""

import json

import sqlalchemy as sa
from alembic import op

from app.config import settings

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

PATH_CONDITIONING = "PATH_CONDITIONING"


def _run(conn, sql: str, params: dict):
    return conn.execute(sa.text(sql), params)


def upgrade() -> None:
    seed = json.loads(settings.seed_path.read_text(encoding="utf-8"))
    conn = op.get_bind()

    ids: dict[str, int] = {}
    for e in seed["exercises"]:
        ids[e["slug"]] = _run(
            conn,
            "INSERT INTO exercises (slug, name, equipment, needs_garage_space, increment_lb, is_timed) "
            "VALUES (:slug, :name, :equipment, :ngs, :inc, :timed) RETURNING id",
            {
                "slug": e["slug"],
                "name": e["name"],
                "equipment": e["equipment"],
                "ngs": e["needs_garage_space"],
                "inc": e["increment_lb"],
                "timed": e["is_timed"],
            },
        ).scalar_one()
    for e in seed["exercises"]:
        if e["swap"]:
            _run(
                conn,
                "UPDATE exercises SET swap_exercise_id = :swap WHERE id = :id",
                {"swap": ids[e["swap"]], "id": ids[e["slug"]]},
            )

    p = seed["program"]
    prog = _run(
        conn,
        "INSERT INTO programs (slug, version, name) VALUES (:slug, :version, :name) RETURNING id",
        {"slug": p["slug"], "version": p["version"], "name": p["name"]},
    ).scalar_one()

    for ph in seed["phases"]:
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

    for st in seed["session_templates"]:
        uses_path_conditioning = any(pr["exercise"] == PATH_CONDITIONING for pr in st["prescriptions"])
        tid = _run(
            conn,
            "INSERT INTO session_templates (program_id, code, name, short_name, kind, day_of_week, "
            "gets_path_techniques, required_for_full_week, uses_path_conditioning) VALUES (:prog, :code, "
            ":name, :short, CAST(:kind AS session_kind), :dow, :gpt, :required, :upc) RETURNING id",
            {
                "prog": prog,
                "code": st["code"],
                "name": st["name"],
                "short": st["short"],
                "kind": st["kind"],
                "dow": st["day_of_week"],
                "gpt": st["gets_path_techniques"],
                "required": st["required_for_full_week"],
                "upc": uses_path_conditioning,
            },
        ).scalar_one()
        for i, pr in enumerate(st["prescriptions"], 1):
            if pr["exercise"] == PATH_CONDITIONING:
                continue  # filled at build time from paths.conditioning_exercise_id
            _run(
                conn,
                "INSERT INTO prescriptions (session_template_id, exercise_id, ord, sets, rep_min, rep_max, "
                "rest_seconds, superset_group, is_main_lift, note) VALUES (:tid, :ex, :ord, :sets, :rep_min, "
                ":rep_max, :rest, :superset, :main, :note)",
                {
                    "tid": tid,
                    "ex": ids[pr["exercise"]],
                    "ord": i,
                    "sets": pr["sets"],
                    "rep_min": pr["rep_min"],
                    "rep_max": pr["rep_max"],
                    "rest": pr["rest_seconds"],
                    "superset": pr.get("superset_group"),
                    "main": pr["is_main_lift"],
                    "note": pr.get("note"),
                },
            )

    for pa in seed["paths"]:
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

    for b in seed["badges"]:
        _run(
            conn,
            "INSERT INTO badges (slug, name, description, xp_reward, rule) "
            "VALUES (:slug, :name, :description, :xp, CAST(:rule AS jsonb))",
            {
                "slug": b["slug"],
                "name": b["name"],
                "description": b["description"],
                "xp": b["xp_reward"],
                "rule": json.dumps(b["rule"]),
            },
        )


def downgrade() -> None:
    for table in [
        "user_badges",
        "badges",
        "path_techniques",
        "prescriptions",
        "session_templates",
        "phases",
        "paths",
        "exercises",
        "programs",
    ]:
        op.execute(f"DELETE FROM {table}")
