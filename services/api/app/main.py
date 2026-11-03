from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import DEV_AUTH_ENVS
from app.api.errors import install_error_handlers
from app.api.v1 import router as v1_router
from app.config import settings

app = FastAPI(title="Ki Forge API", version="0.1.0")
install_error_handlers(app)
app.include_router(v1_router)

if settings.app_env in DEV_AUTH_ENVS:
    # The Expo web build runs on another port (8081) of the same PC; only local dev needs this.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["ETag"],
    )


@app.get("/healthz", tags=["meta"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}
