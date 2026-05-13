from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from api.routes.compare import compare_prices
from db.models import Base, Product, SourceEnum, CategoryEnum


@pytest.mark.asyncio
async def test_compare_prices_uses_latest_db_snapshot(tmp_path):
    db_path = tmp_path / "compare.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    old_ts = datetime(2026, 5, 13, 0, 0, tzinfo=timezone.utc)
    new_ts = datetime(2026, 5, 13, 1, 0, tzinfo=timezone.utc)

    rows = [
        Product(
            source=SourceEnum.danawa,
            category=CategoryEnum.memory,
            name="OLD Danawa 8GB",
            price=100000,
            rank=99,
            crawled_at=old_ts,
        ),
        Product(
            source=SourceEnum.smtcom,
            category=CategoryEnum.memory,
            name="OLD Smtcom 8GB",
            price=90000,
            rank=None,
            crawled_at=old_ts,
        ),
        Product(
            source=SourceEnum.danawa,
            category=CategoryEnum.memory,
            name="삼성전자 DDR5-5600 (16GB)",
            price=150000,
            rank=1,
            crawled_at=new_ts,
        ),
        Product(
            source=SourceEnum.smtcom,
            category=CategoryEnum.memory,
            name="삼성전자 DDR5-5600 (16GB) PC5-44800",
            price=145000,
            rank=None,
            crawled_at=new_ts,
        ),
    ]

    async with session_factory() as session:
        session.add_all(rows)
        await session.commit()

    async with session_factory() as session:
        response = await compare_prices(
            category="memory",
            sort="popular",
            ddr=None,
            ecc_exclude=False,
            capacity_gb=None,
            db=session,
        )

    assert response.total == 1
    assert response.matched == 1
    assert response.items[0].danawa_name == "삼성전자 DDR5-5600 (16GB)"
    assert response.items[0].smtcom_name == "삼성전자 DDR5-5600 (16GB) PC5-44800"
    assert response.items[0].price_diff == -5000
