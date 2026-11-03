import pytest

from app.config import settings
from app.rules.program import Program, load_program


@pytest.fixture(scope="session")
def program() -> Program:
    return load_program(settings.seed_path)
