from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, asc
from db.models import Product, CrawlLog, SourceEnum, CategoryEnum


async def upsert_products(session: AsyncSession, products: list[dict]):
    for p in products:
        session.add(Product(**p))
    await session.commit()


async def get_latest_products(
    session: AsyncSession,
    category: CategoryEnum,
    source: SourceEnum,
) -> list[Product]:
    subq = (
        select(func.max(Product.crawled_at))
        .where(Product.source == source, Product.category == category)
        .scalar_subquery()
    )
    result = await session.execute(
        select(Product).where(
            Product.source == source,
            Product.category == category,
            Product.crawled_at == subq,
        )
    )
    return result.scalars().all()


async def get_last_crawled_at(
    session: AsyncSession,
    category: CategoryEnum,
) -> datetime | None:
    result = await session.execute(
        select(func.max(Product.crawled_at)).where(
            Product.source == SourceEnum.danawa,
            Product.category == category,
        )
    )
    return result.scalar()


async def create_crawl_log(
    session: AsyncSession,
    source: SourceEnum,
    category: CategoryEnum,
) -> CrawlLog:
    log = CrawlLog(
        source=source,
        category=category,
        started_at=datetime.now(timezone.utc),
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def finish_crawl_log(
    session: AsyncSession,
    log_id: int,
    status: str,
    item_count: int = 0,
    error_message: str | None = None,
):
    result = await session.execute(select(CrawlLog).where(CrawlLog.id == log_id))
    log = result.scalar_one()
    log.finished_at = datetime.now(timezone.utc)
    log.status = status
    log.item_count = item_count
    log.error_message = error_message
    await session.commit()
