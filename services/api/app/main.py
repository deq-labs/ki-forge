from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.v1 import router as v1_router

app = FastAPI(title="Ki Forge API", version="0.1.0")
install_error_handlers(app)
app.include_router(v1_router)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}
