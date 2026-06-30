import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from dotenv import load_dotenv
from sqlalchemy import text

from db.database import init_db, AsyncSessionLocal
from api.routes import admin, compare, estimates, trend
from scheduler.jobs import create_scheduler, crawl_all

load_dotenv()

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"


class NoCacheStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


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
app.include_router(estimates.router, prefix="/api")
app.include_router(admin.router, prefix="/api")

# 프론트엔드 정적 파일
app.mount("/static", NoCacheStaticFiles(directory=str(FRONTEND_DIR)), name="static")
app.mount("/html", NoCacheStaticFiles(directory=str(BASE_DIR / "HTML")), name="html")


@app.get("/")
async def root():
    response = FileResponse(str(FRONTEND_DIR / "index.html"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/admin/login")
async def admin_login():
    response = FileResponse(str(FRONTEND_DIR / "admin-login.html"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/admin")
async def admin_root(request: Request):
    if not admin.is_admin_request(request):
        return RedirectResponse("/admin/login", status_code=303)
    response = FileResponse(str(FRONTEND_DIR / "admin.html"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


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
