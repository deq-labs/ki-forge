"""Load db/seed/program.json into a database created from db/0001_initial.sql.

Usage: python db/load_seed.py postgresql://user:pass@localhost:5432/kiforge
This is the reference loader; the real app should port it to an Alembic data migration.
"""
import json, sys, pathlib
import psycopg

seed = json.loads((pathlib.Path(__file__).parent / "seed" / "program.json").read_text(encoding="utf-8"))

with psycopg.connect(sys.argv[1]) as conn, conn.cursor() as cur:
    ids = {}
    for e in seed["exercises"]:
        cur.execute("INSERT INTO exercises (slug, name, equipment, needs_garage_space, increment_lb, is_timed) "
                    "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (e["slug"], e["name"], e["equipment"], e["needs_garage_space"], e["increment_lb"], e["is_timed"]))
        ids[e["slug"]] = cur.fetchone()[0]
    for e in seed["exercises"]:
        if e["swap"]:
            cur.execute("UPDATE exercises SET swap_exercise_id=%s WHERE id=%s", (ids[e["swap"]], ids[e["slug"]]))
    p = seed["program"]
    cur.execute("INSERT INTO programs (slug, version, name) VALUES (%s,%s,%s) RETURNING id", (p["slug"], p["version"], p["name"]))
    prog = cur.fetchone()[0]
    for ph in seed["phases"]:
        cur.execute("INSERT INTO phases (program_id, ord, name, display_name_template, kind, start_week, end_week, rir_target, "
                    "deload_every, calorie_mode, modifiers) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (prog, ph["ord"], ph["name"], ph.get("display_name_template"), ph["kind"], ph["start_week"], ph["end_week"],
                     ph["rir_target"], ph["deload_every"], ph["calorie_mode"], json.dumps(ph["modifiers"])))
    for st in seed["session_templates"]:
        uses_path_conditioning = any(pr["exercise"] == "PATH_CONDITIONING" for pr in st["prescriptions"])
        cur.execute("INSERT INTO session_templates (program_id, code, name, short_name, kind, day_of_week, gets_path_techniques, "
                    "required_for_full_week, uses_path_conditioning) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (prog, st["code"], st["name"], st["short"], st["kind"], st["day_of_week"], st["gets_path_techniques"],
                     st["required_for_full_week"], uses_path_conditioning))
        tid = cur.fetchone()[0]
        for i, pr in enumerate(st["prescriptions"], 1):
            if pr["exercise"] == "PATH_CONDITIONING":
                continue  # resolved at runtime from paths.conditioning_exercise_id
            cur.execute("INSERT INTO prescriptions (session_template_id, exercise_id, ord, sets, rep_min, rep_max, rest_seconds, "
                        "superset_group, is_main_lift, note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (tid, ids[pr["exercise"]], i, pr["sets"], pr["rep_min"], pr["rep_max"], pr["rest_seconds"],
                         pr.get("superset_group"), pr["is_main_lift"], pr.get("note")))
    for pa in seed["paths"]:
        cur.execute("INSERT INTO paths (slug, name, tagline, build, ratio_target, colors, emphasis, conditioning_exercise_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (pa["slug"], pa["name"], pa["tagline"], pa["build"], pa["ratio_target"], json.dumps(pa["colors"]),
                     json.dumps(pa["emphasis"]), ids[pa["conditioning_exercise"]]))
        pid = cur.fetchone()[0]
        for i, t in enumerate(pa["techniques"], 1):
            cur.execute("INSERT INTO path_techniques (path_id, exercise_id, ord, sets, rep_min, rep_max, note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (pid, ids[t["exercise"]], i, t["sets"], t["rep_min"], t["rep_max"], t.get("note")))
    for b in seed["badges"]:
        cur.execute("INSERT INTO badges (slug, name, description, xp_reward, rule) VALUES (%s,%s,%s,%s,%s)",
                    (b["slug"], b["name"], b["description"], b["xp_reward"], json.dumps(b["rule"])))
    conn.commit()
print("seed loaded")
