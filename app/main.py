import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth.router import router as auth_router
from app.images.router import router as images_router

logger = logging.getLogger(__name__)

app = FastAPI(title="Image Processing Service")

app.include_router(auth_router)
app.include_router(images_router, prefix="/images")


@app.get("/")
async def root():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
