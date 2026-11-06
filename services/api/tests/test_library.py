"""Exercise library (free-exercise-db): seed file, program.json links, photos, GET /v1/library (#74)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.rules.program import Program
from app.services.library import JSDELIVR, get_library, search


def test_library_file_is_pinned_and_complete() -> None:
    data = json.loads(settings.library_path.read_text(encoding="utf-8"))
    assert len(data["commit"]) == 40 and data["license"].startswith("Unlicense")
    library = get_library()
    assert len(library.exercises) == len(data["exercises"]) > 800
    assert sum(not e.images for e in library.exercises.values()) <= 5  # a few upstream entries have no photos


def test_every_program_link_exists(program: Program) -> None:
    library = get_library()
    links = {s: e.library for s, e in program.exercises.items() if e.library}
    assert not [s for s, ref in links.items() if ref not in library.exercises]
    assert len(links) >= 70
    assert links["barbell-back-squat"] == "Barbell_Squat"
    # X3 band-bar work has no honest photo in the library; leave it unlinked rather than show a barbell.
    assert not [s for s in links if s.startswith("x3-")]


def test_image_urls_default_to_the_pinned_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    library = get_library()
    monkeypatch.setattr(settings, "exercise_images_base_url", "")
    assert library.image_urls("Barbell_Squat") == [
        JSDELIVR.format(commit=library.commit) + "Barbell_Squat/0.jpg",
        JSDELIVR.format(commit=library.commit) + "Barbell_Squat/1.jpg",
    ]
    monkeypatch.setattr(settings, "exercise_images_base_url", "https://img.example.com/ex")
    assert library.image_urls("Barbell_Squat")[0] == "https://img.example.com/ex/Barbell_Squat/0.jpg"
    assert library.image_urls(None) == [] and library.image_urls("nope") == []


def test_search_matches_all_words_and_filters() -> None:
    library = get_library()
    names = [e.name for e in search(library, "dumbbell press incline")]
    assert "Incline Dumbbell Press" in names and all("incline" in n.lower() for n in names)
    assert all(e.equipment == "kettlebells" for e in search(library, equipment="kettlebells"))
    hits = search(library, muscle="hamstrings")
    assert hits and all("hamstrings" in e.primary_muscles + e.secondary_muscles for e in hits)
    assert [e.name for e in hits] == sorted((e.name for e in hits), key=str.lower)


def test_program_exercises_carry_photos(client: TestClient) -> None:
    body = client.get("/v1/program").json()
    ex = {e["slug"]: e for e in body["exercises"]}
    squat = ex["barbell-back-squat"]
    assert squat["library"] == "Barbell_Squat"
    assert [u.rsplit("/", 2)[-2:] for u in squat["images"]] == [
        ["Barbell_Squat", "0.jpg"],
        ["Barbell_Squat", "1.jpg"],
    ]
    assert "quadriceps" in squat["muscles"]
    assert ex["x3-bar-squat"]["images"] == [] and ex["x3-bar-squat"]["library"] is None


def test_program_etag_follows_the_image_host(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    before = client.get("/v1/program").headers["etag"]
    monkeypatch.setattr(settings, "exercise_images_base_url", "https://img.example.com/")
    after = client.get("/v1/program")
    assert after.headers["etag"] != before
    assert after.json()["exercises"][1]["images"][0].startswith("https://img.example.com/")


def test_library_endpoint_pages_and_links() -> None:
    from app.main import app

    with TestClient(app) as anon:  # reference data: no sign-in needed
        page = anon.get("/v1/library", params={"q": "barbell squat", "limit": 3}).json()
        assert page["total"] >= 3 and len(page["items"]) == 3
        assert "barbell" in page["equipment"] and "quadriceps" in page["muscles"]
        more = anon.get("/v1/library", params={"q": "barbell squat", "limit": 3, "offset": 3}).json()
        assert not {i["id"] for i in page["items"]} & {i["id"] for i in more["items"]}

        squat = anon.get("/v1/library/Barbell_Squat").json()
        assert squat["program_exercise"] in {"barbell-back-squat", "paused-back-squat"}
        assert squat["instructions"] and len(squat["images"]) == 2
        assert anon.get("/v1/library/Nope").status_code == 404
        assert anon.get("/v1/library", params={"limit": 500}).status_code == 422
