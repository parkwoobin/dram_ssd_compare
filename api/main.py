import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from db.database import init_db
from api.routes import compare, trend
from scheduler.jobs import create_scheduler, crawl_all

load_dotenv()

logger = logging.getLogger(__name__)


async def _initial_crawl():
    """서버 시작 시 Product 테이블이 비어 있으면 즉시 크롤링 실행."""
    from db.database import AsyncSessionLocal
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
    scheduler = create_scheduler()
    scheduler.start()
    asyncio.create_task(_initial_crawl())
    yield
    scheduler.shutdown()


app = FastAPI(title="DRAM & SSD 가격 비교", lifespan=lifespan)

app.include_router(compare.router, prefix="/api")
app.include_router(trend.router, prefix="/api")

# 프론트엔드 정적 파일
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}
