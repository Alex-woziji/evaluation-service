import logging
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from app.api.v1.evaluate import router as eval_router
from app.utils.config import app_settings

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, app_settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Evaluation Service",
    description="LLM evaluation metric calculation layer",
    version=app_settings.app_version,
)

app.include_router(eval_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
