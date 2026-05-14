import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from crawler.danawa import crawl as danawa_crawl, CATEGORIES as DANAWA_CATS
from crawler.smtcom import crawl as smtcom_crawl
from db.database import AsyncSessionLocal
from db.models import SourceEnum, CategoryEnum
from db.crud import (
    upsert_products,
    create_crawl_log,
    finish_crawl_log,
    aggregate_daily_prices,
    prune_old_products,
)

logger = logging.getLogger(__name__)

CRAWL_START_HOUR = int(os.getenv("CRAWL_START_HOUR", 9))
CRAWL_END_HOUR = int(os.getenv("CRAWL_END_HOUR", 18))
PRODUCT_RETENTION_DAYS = int(os.getenv("PRODUCT_RETENTION_DAYS", 7))


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
        aggregate_daily,
        CronTrigger(hour=18, minute="5", timezone="Asia/Seoul"),
        id="aggregate_daily",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler
