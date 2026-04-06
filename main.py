from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.images.router import router as images_router

app = FastAPI()

app.include_router(auth_router)
app.include_router(images_router, prefix="/images")


@app.get("/")
async def root():
    return {"message": "Hello World"}
