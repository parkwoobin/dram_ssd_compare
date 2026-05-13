import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from sqlalchemy import text

from db.database import init_db, AsyncSessionLocal
from api.routes import compare, trend
from scheduler.jobs import create_scheduler, crawl_all

load_dotenv()

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"


def _env_true(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


async def _initial_crawl():
    """서버 시작 시 Product 테이블이 비어 있으면 즉시 크롤링 실행."""
    from db.models import Product
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        count = await session.execute(select(func.count()).select_from(Product))
        if count.scalar() == 0:
            logger.info("DB 비어 있음 - 초기 크롤링 실행")
            await crawl_all(force=True)
        else:
            logger.info("DB 데이터 있음 - 초기 크롤링 생략")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    scheduler = None
    if _env_true("ENABLE_SCHEDULER", "true"):
        scheduler = create_scheduler()
        scheduler.start()
        logger.info("Scheduler started")
    else:
        logger.info("Scheduler disabled by ENABLE_SCHEDULER")

    if _env_true("ENABLE_INITIAL_CRAWL", "true"):
        asyncio.create_task(_initial_crawl())
    else:
        logger.info("Initial crawl disabled by ENABLE_INITIAL_CRAWL")

    yield

    if scheduler is not None:
        scheduler.shutdown()


app = FastAPI(title="DRAM & SSD 가격 비교", lifespan=lifespan)

app.include_router(compare.router, prefix="/api")
app.include_router(trend.router, prefix="/api")

# 프론트엔드 정적 파일
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def root():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(str(FRONTEND_DIR / "favicon.svg"), media_type="image/svg+xml")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "reason": str(e)})
