"""The exercise library: reference data from free-exercise-db (public domain).

`db/seed/exercise_library.json` is written by `pnpm import:library` at a pinned commit. It is reference
content only (names, muscles, instructions, photos): nothing here feeds the rules engine, and library
exercises can't be logged. Program exercises point at an entry with `library` in program.json.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.config import settings

JSDELIVR = "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@{commit}/exercises/"


@dataclass(frozen=True, slots=True)
class LibraryExercise:
    id: str
    name: str
    category: str
    equipment: str | None
    level: str
    force: str | None
    mechanic: str | None
    primary_muscles: tuple[str, ...]
    secondary_muscles: tuple[str, ...]
    instructions: tuple[str, ...]
    images: tuple[str, ...]  # paths relative to the image base URL


@dataclass(frozen=True)
class Library:
    commit: str
    digest: str
    exercises: dict[str, LibraryExercise]

    @property
    def image_base(self) -> str:
        base = settings.exercise_images_base_url or JSDELIVR.format(commit=self.commit)
        return base if base.endswith("/") else base + "/"

    def image_urls(self, library_id: str | None) -> list[str]:
        entry = self.exercises.get(library_id) if library_id else None
        return [self.image_base + p for p in entry.images] if entry else []

    def muscles(self, library_id: str | None) -> list[str]:
        entry = self.exercises.get(library_id) if library_id else None
        return list(entry.primary_muscles) if entry else []


@cache
def _load(path: Path) -> Library:
    raw = path.read_bytes()
    data = json.loads(raw)
    exercises = {
        e["id"]: LibraryExercise(
            id=e["id"],
            name=e["name"],
            category=e["category"],
            equipment=e["equipment"],
            level=e["level"],
            force=e["force"],
            mechanic=e["mechanic"],
            primary_muscles=tuple(e["primary_muscles"]),
            secondary_muscles=tuple(e["secondary_muscles"]),
            instructions=tuple(e["instructions"]),
            images=tuple(e["images"]),
        )
        for e in data["exercises"]
    }
    return Library(commit=data["commit"], digest=hashlib.sha256(raw).hexdigest()[:12], exercises=exercises)


def get_library() -> Library:
    return _load(settings.library_path)


def search(
    library: Library, q: str | None = None, equipment: str | None = None, muscle: str | None = None
) -> list[LibraryExercise]:
    """Entries matching every given filter, by name. `q` matches all of its words anywhere in the name."""
    words = (q or "").lower().split()
    out = []
    for e in library.exercises.values():
        name = e.name.lower()
        if words and not all(w in name for w in words):
            continue
        if equipment and (e.equipment or "") != equipment:
            continue
        if muscle and muscle not in e.primary_muscles and muscle not in e.secondary_muscles:
            continue
        out.append(e)
    return sorted(out, key=lambda e: e.name.lower())
