"""GET /v1/library: browse and search the exercise library (free-exercise-db, public domain)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response

from app.api.errors import ApiError
from app.api.schemas import LibraryExerciseOut, LibraryPage
from app.services.library import LibraryExercise, get_library, search
from app.services.program import get_program

router = APIRouter(tags=["library"])


def _out(e: LibraryExercise, image_base: str, in_program: dict[str, str]) -> LibraryExerciseOut:
    return LibraryExerciseOut(
        id=e.id,
        name=e.name,
        category=e.category,
        equipment=e.equipment,
        level=e.level,
        force=e.force,
        mechanic=e.mechanic,
        primary_muscles=list(e.primary_muscles),
        secondary_muscles=list(e.secondary_muscles),
        instructions=list(e.instructions),
        images=[image_base + p for p in e.images],
        program_exercise=in_program.get(e.id),
    )


def _in_program() -> dict[str, str]:
    """Library id -> the first program exercise slug that uses it."""
    out: dict[str, str] = {}
    for ex in get_program().exercises.values():
        if ex.library:
            out.setdefault(ex.library, ex.slug)
    return out


@router.get("/library", response_model=LibraryPage)
def list_library(
    response: Response,
    q: str | None = Query(None, max_length=80, description="Words that must all appear in the name"),
    equipment: str | None = Query(None, max_length=40),
    muscle: str | None = Query(None, max_length=40),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> LibraryPage:
    """Library exercises matching every filter, sorted by name, one page at a time."""
    library = get_library()
    response.headers["Cache-Control"] = "public, max-age=3600"
    hits = search(library, q, equipment, muscle)
    in_program = _in_program()
    base = library.image_base
    return LibraryPage(
        total=len(hits),
        commit=library.commit,
        items=[_out(e, base, in_program) for e in hits[offset : offset + limit]],
        equipment=sorted({e.equipment for e in library.exercises.values() if e.equipment}),
        muscles=sorted({m for e in library.exercises.values() for m in e.primary_muscles}),
    )


@router.get("/library/{library_id}", response_model=LibraryExerciseOut)
def read_library_exercise(library_id: str) -> LibraryExerciseOut:
    library = get_library()
    entry = library.exercises.get(library_id)
    if entry is None:
        raise ApiError(404, "not_found", f"no library exercise {library_id!r}")
    return _out(entry, library.image_base, _in_program())
