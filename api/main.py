import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from db.database import init_db
from api.routes import compare
from scheduler.jobs import create_scheduler

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler = create_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="DRAM & SSD 가격 비교", lifespan=lifespan)

app.include_router(compare.router, prefix="/api")

# 프론트엔드 정적 파일
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}
