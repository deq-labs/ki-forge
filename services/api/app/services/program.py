"""The program the API serves.

Program content is data from `db/seed/program.json` (CLAUDE.md rule 2). The DB holds the same seed
(migration 0002) for foreign keys, but drops a few things the rules need (ranks, test definitions,
cycle length, the PATH_CONDITIONING slot), so the rules `Program` is loaded from the seed file and the
DB is used only to map slugs to row ids. `program_ids` checks that the DB was seeded with the same
program version.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cache, cached_property
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BadgeRow, ExerciseRow, PathRow, PhaseRow, ProgramRow, SessionTemplateRow
from app.rules.program import Program, load_program


@cache
def _load(path: Path) -> tuple[Program, str]:
    raw = path.read_bytes()
    return load_program(path), hashlib.sha256(raw).hexdigest()[:12]


def get_program() -> Program:
    return _load(settings.seed_path)[0]


def program_etag() -> str:
    program, digest = _load(settings.seed_path)
    return f'W/"{program.slug}-v{program.version}-{digest}"'


@dataclass(frozen=True)
class ProgramIds:
    """DB row ids for the program's content, by slug / code / ord."""

    program_id: int
    exercises: dict[str, int]
    templates: dict[str, int]
    phases: dict[int, int]  # by ord
    paths: dict[str, int]
    badges: dict[str, int]

    def exercise_slug(self, exercise_id: int) -> str:
        return self._exercise_slugs[exercise_id]

    def path_slug(self, path_id: int) -> str:
        return self._path_slugs[path_id]

    def template_code(self, template_id: int) -> str:
        return self._template_codes[template_id]

    def phase_ord(self, phase_id: int) -> int:
        return self._phase_ords[phase_id]

    @cached_property
    def _exercise_slugs(self) -> dict[int, str]:
        return {v: k for k, v in self.exercises.items()}

    @cached_property
    def _path_slugs(self) -> dict[int, str]:
        return {v: k for k, v in self.paths.items()}

    @cached_property
    def _template_codes(self) -> dict[int, str]:
        return {v: k for k, v in self.templates.items()}

    @cached_property
    def _phase_ords(self) -> dict[int, int]:
        return {v: k for k, v in self.phases.items()}


class ProgramNotSeeded(RuntimeError):
    pass


_ids_cache: dict[tuple[str, str, int], ProgramIds] = {}


def program_ids(db: Session) -> ProgramIds:
    """Row ids for the served program in this database (cached per database URL and program version)."""
    program = get_program()
    key = (str(db.get_bind().engine.url), program.slug, program.version)
    if key in _ids_cache:
        return _ids_cache[key]
    program_id = db.scalar(
        select(ProgramRow.id).where(ProgramRow.slug == program.slug, ProgramRow.version == program.version)
    )
    if program_id is None:
        raise ProgramNotSeeded(
            f"program {program.slug} v{program.version} is not in the database; run `alembic upgrade head`"
        )

    def pairs(stmt) -> dict:
        return {k: v for k, v in db.execute(stmt).all()}

    ids = ProgramIds(
        program_id=program_id,
        exercises=pairs(select(ExerciseRow.slug, ExerciseRow.id)),
        templates=pairs(
            select(SessionTemplateRow.code, SessionTemplateRow.id).where(
                SessionTemplateRow.program_id == program_id
            )
        ),
        phases=pairs(select(PhaseRow.ord, PhaseRow.id).where(PhaseRow.program_id == program_id)),
        paths=pairs(select(PathRow.slug, PathRow.id)),
        badges=pairs(select(BadgeRow.slug, BadgeRow.id)),
    )
    missing = (
        [f"exercise {s}" for s in program.exercises if s not in ids.exercises]
        + [f"template {t.code}" for t in program.session_templates if t.code not in ids.templates]
        + [f"phase {p.ord}" for p in program.phases if p.ord not in ids.phases]
        + [f"path {s}" for s in program.paths if s not in ids.paths]
        + [f"badge {b.slug}" for b in program.badges if b.slug not in ids.badges]
    )
    if missing:
        raise ProgramNotSeeded(f"database seed differs from program.json: missing {', '.join(missing)}")
    _ids_cache[key] = ids
    return ids
