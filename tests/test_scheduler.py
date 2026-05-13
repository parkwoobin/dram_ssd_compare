from datetime import datetime, date, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func

from db.models import Base, Product, DailyPrice, SourceEnum, CategoryEnum
from scheduler.jobs import create_scheduler, aggregate_daily
import scheduler.jobs as jobs_module


@pytest.mark.asyncio
async def test_create_scheduler_runs_hourly_on_the_hour():
    scheduler = create_scheduler()
    crawl_job = scheduler.get_job("crawl_all")
    aggregate_job = scheduler.get_job("aggregate_daily")

    assert crawl_job is not None
    assert aggregate_job is not None
    assert str(crawl_job.trigger.fields[5]) == "*"
    assert str(crawl_job.trigger.fields[6]) == "0"
    assert str(aggregate_job.trigger.fields[5]) == "0"
    assert str(aggregate_job.trigger.fields[6]) == "5"


@pytest.mark.asyncio
async def test_aggregate_daily_prices_persists_daily_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "test_prices.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(jobs_module, "AsyncSessionLocal", session_factory)

    target_day = date(2026, 5, 12)
    samples = [
        Product(
            source=SourceEnum.danawa,
            category=CategoryEnum.memory,
            name="삼성전자 DDR5-5600 (16GB)",
            price=350000,
            rank=1,
            crawled_at=datetime(2026, 5, 11, 16, 0, tzinfo=timezone.utc),
        ),
        Product(
            source=SourceEnum.danawa,
            category=CategoryEnum.memory,
            name="삼성전자 DDR5-5600 (16GB)",
            price=340000,
            rank=1,
            crawled_at=datetime(2026, 5, 12, 2, 0, tzinfo=timezone.utc),
        ),
        Product(
            source=SourceEnum.smtcom,
            category=CategoryEnum.memory,
            name="삼성전자 DDR5-5600 (16GB) PC5-44800",
            price=330000,
            rank=None,
            crawled_at=datetime(2026, 5, 12, 2, 0, tzinfo=timezone.utc),
        ),
    ]

    async with session_factory() as session:
        session.add_all(samples)
        await session.commit()

    async with session_factory() as session:
        count = await aggregate_daily(target_date=target_day)

    async with session_factory() as session:
        rows = (await session.execute(select(DailyPrice))).scalars().all()

    assert count == 2
    assert len(rows) == 2

    danawa_row = next(r for r in rows if r.source == SourceEnum.danawa)
    assert danawa_row.date == target_day
    assert danawa_row.avg_price == pytest.approx(345000)
    assert danawa_row.min_price == 340000
    assert danawa_row.max_price == 350000
    assert danawa_row.crawl_count == 2
