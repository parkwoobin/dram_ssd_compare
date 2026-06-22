import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.engine import make_url

from crawler.danawa import crawl as danawa_crawl, CATEGORIES as DANAWA_CATS
from crawler.smtcom import crawl as smtcom_crawl
from db.database import AsyncSessionLocal, DATABASE_URL
from db.models import SourceEnum, CategoryEnum
from db.crud import (
    upsert_products,
    create_crawl_log,
    finish_crawl_log,
    aggregate_daily_prices,
    seed_daily_prices_from_previous_day,
    prune_old_products,
)

logger = logging.getLogger(__name__)

CRAWL_START_HOUR = int(os.getenv("CRAWL_START_HOUR", 9))
CRAWL_END_HOUR = int(os.getenv("CRAWL_END_HOUR", 18))
PRODUCT_RETENTION_DAYS = int(os.getenv("PRODUCT_RETENTION_DAYS", 7))
DB_BACKUP_HOUR = int(os.getenv("DB_BACKUP_HOUR", 0))
DB_BACKUP_DIR = Path(os.getenv("DB_BACKUP_DIR", "./data/backups"))
DB_BACKUP_RETENTION_DAYS = int(os.getenv("DB_BACKUP_RETENTION_DAYS", 14))


async def _run_crawl(source: SourceEnum, category: str):
    cat_enum = CategoryEnum(category)
    async with AsyncSessionLocal() as session:
        log = await create_crawl_log(session, source, cat_enum)

    try:
        if source == SourceEnum.danawa:
            products_raw = await danawa_crawl(category)
        else:
            products_raw = await smtcom_crawl(category)

        now = datetime.now(timezone.utc)
        products_db = [
            {
                "source": source,
                "category": cat_enum,
                "name": p["name"],
                "price": p.get("price"),
                "rank": p.get("rank"),
                "crawled_at": now,
            }
            for p in products_raw
        ]

        async with AsyncSessionLocal() as session:
            await upsert_products(session, products_db)
            await finish_crawl_log(session, log.id, "success", len(products_db))

        logger.info("[%s][%s] %d개 수집 완료", source.value, category, len(products_db))

    except Exception as e:
        logger.error("[%s][%s] 크롤링 실패: %s", source.value, category, e)
        async with AsyncSessionLocal() as session:
            await finish_crawl_log(session, log.id, "failed", error_message=str(e))


async def crawl_all(force: bool = False):
    """다나와·스마트컴 메모리·SSD 전체 크롤링. force=True 이면 시간 제한 무시."""
    hour = (datetime.now(timezone.utc) + timedelta(hours=9)).hour
    if not force and not (CRAWL_START_HOUR <= hour < CRAWL_END_HOUR):
        logger.debug("크롤링 시간 외 (%d시 KST)", hour)
        return

    logger.info("크롤링 시작 (%d시 KST)%s", hour, " [초기 강제]" if force else "")
    tasks = []
    for category in ("memory", "ssd"):
        tasks.append(_run_crawl(SourceEnum.danawa, category))
        tasks.append(_run_crawl(SourceEnum.smtcom, category))
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("크롤링 완료")


async def aggregate_daily(target_date=None):
    """하루치 가격 데이터 집계. 기본값은 KST 기준 오늘."""
    logger.info("일별 가격 집계 시작")
    try:
        if target_date is None:
            target_date = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
        async with AsyncSessionLocal() as session:
            count = await aggregate_daily_prices(session, target_date=target_date)
            pruned = await prune_old_products(session, retention_days=PRODUCT_RETENTION_DAYS)
        logger.info(
            "일별 가격 집계 완료: %d개 레코드, products 정리: %d개 삭제 (%d일 보관)",
            count,
            pruned,
            PRODUCT_RETENTION_DAYS,
        )
        return count
    except Exception as e:
        logger.error("일별 가격 집계 실패: %s", e)
        return 0


async def seed_today_prices(target_date=None):
    """자정에 전날 확정 가격을 오늘 임시 가격으로 복사."""
    logger.info("오늘 가격 기준값 복사 시작")
    try:
        if target_date is None:
            target_date = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
        async with AsyncSessionLocal() as session:
            count = await seed_daily_prices_from_previous_day(session, target_date=target_date)
        logger.info("오늘 가격 기준값 복사 완료: %d개 레코드", count)
        return count
    except Exception as e:
        logger.error("오늘 가격 기준값 복사 실패: %s", e)
        return 0


def _sqlite_database_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return None
    if not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


async def backup_database(now: datetime | None = None) -> str | None:
    """SQLite DB를 안전하게 백업하고 오래된 백업을 정리한다."""
    db_path = _sqlite_database_path(DATABASE_URL)
    if db_path is None:
        logger.warning("DB 백업 건너뜀: SQLite 파일 DB가 아님 (%s)", DATABASE_URL)
        return None
    if not db_path.exists():
        logger.warning("DB 백업 건너뜀: DB 파일 없음 (%s)", db_path)
        return None

    if now is None:
        now = datetime.now(timezone.utc) + timedelta(hours=9)

    DB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = DB_BACKUP_DIR / f"prices-{now.strftime('%Y%m%d-%H%M%S')}.db"

    source = sqlite3.connect(db_path)
    try:
        dest = sqlite3.connect(backup_path)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()

    cutoff = now - timedelta(days=DB_BACKUP_RETENTION_DAYS)
    for old_backup in DB_BACKUP_DIR.glob("prices-*.db"):
        try:
            modified = datetime.fromtimestamp(old_backup.stat().st_mtime, tz=timezone.utc) + timedelta(hours=9)
            if modified < cutoff:
                old_backup.unlink()
        except OSError as e:
            logger.warning("오래된 DB 백업 정리 실패 (%s): %s", old_backup, e)

    logger.info("DB 백업 완료: %s", backup_path)
    return str(backup_path)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        crawl_all,
        CronTrigger(
            hour="*",
            minute="0",
            timezone="Asia/Seoul",
        ),
        id="crawl_all",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        seed_today_prices,
        CronTrigger(hour=0, minute="0", timezone="Asia/Seoul"),
        id="seed_today_prices",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        aggregate_daily,
        CronTrigger(hour=18, minute="5", timezone="Asia/Seoul"),
        id="aggregate_daily",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        backup_database,
        CronTrigger(hour=DB_BACKUP_HOUR, minute="0", timezone="Asia/Seoul"),
        id="backup_database",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler
