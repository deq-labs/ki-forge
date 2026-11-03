from fastapi import APIRouter, Request, Response

from app.api.account import router as account_router
from app.api.calendar import router as calendar_router
from app.api.me import router as me_router
from app.api.schemas import ProgramOut
from app.api.sync import router as sync_router
from app.api.trials import router as trials_router
from app.services.program import get_program, program_etag

router = APIRouter(prefix="/v1")
router.include_router(me_router)
router.include_router(calendar_router)
router.include_router(sync_router)
router.include_router(trials_router)
router.include_router(account_router)


@router.get("/program", response_model=ProgramOut, tags=["program"])
def read_program(request: Request, response: Response) -> ProgramOut | Response:
    """Whole program content. Cacheable: send `If-None-Match` with the last ETag to get a 304."""
    etag = program_etag()
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=300"
    program = get_program()
    return ProgramOut.model_validate(
        {
            **{k: getattr(program, k) for k in ("slug", "version", "name", "cycle_weeks")},
            "exercises": list(program.exercises.values()),
            "phases": list(program.phases),
            "session_templates": list(program.session_templates),
            "paths": list(program.paths.values()),
            "tests": list(program.tests),
            "badges": list(program.badges),
            "ranks": list(program.ranks),
        }
    )
