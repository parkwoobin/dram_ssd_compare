import asyncio
import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from crawler.danawa import crawl as danawa_crawl, CATEGORIES as DANAWA_CATS
from crawler.smtcom import crawl as smtcom_crawl
from db.database import AsyncSessionLocal
from db.models import SourceEnum, CategoryEnum
from db.crud import upsert_products, create_crawl_log, finish_crawl_log

logger = logging.getLogger(__name__)

CRAWL_START_HOUR = int(os.getenv("CRAWL_START_HOUR", 9))
CRAWL_END_HOUR = int(os.getenv("CRAWL_END_HOUR", 18))


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


async def crawl_all():
    """다나와·스마트컴 메모리·SSD 전체 크롤링"""
    hour = datetime.now().hour
    if not (CRAWL_START_HOUR <= hour < CRAWL_END_HOUR):
        logger.debug("크롤링 시간 외 (%d시)", hour)
        return

    logger.info("크롤링 시작 (%d시)", hour)
    tasks = []
    for category in ("memory", "ssd"):
        tasks.append(_run_crawl(SourceEnum.danawa, category))
        tasks.append(_run_crawl(SourceEnum.smtcom, category))
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("크롤링 완료")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        crawl_all,
        CronTrigger(
            hour=f"{CRAWL_START_HOUR}-{CRAWL_END_HOUR - 1}",
            minute="0",
            timezone="Asia/Seoul",
        ),
        id="crawl_all",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler
