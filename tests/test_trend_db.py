from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from api.routes.trend import trend_daily_history
from db.models import Base, DailyPrice, Product, SourceEnum, CategoryEnum
from db.crud import get_daily_history, get_trend_products


@pytest.mark.asyncio
async def test_trend_daily_history_uses_saved_daily_prices_only(tmp_path):
    db_path = tmp_path / "trend.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    saved_day = date(2026, 6, 12)
    async with session_factory() as session:
        session.add_all(
            [
                DailyPrice(
                    date=saved_day,
                    source=SourceEnum.danawa,
                    category=CategoryEnum.memory,
                    name="삼성전자 DDR5-5600 (16GB)",
                    avg_price=340000,
                    min_price=330000,
                    max_price=350000,
                    crawl_count=2,
                ),
                DailyPrice(
                    date=saved_day,
                    source=SourceEnum.smtcom,
                    category=CategoryEnum.memory,
                    name="삼성전자 DDR5-5600 (16GB) PC5-44800",
                    avg_price=335000,
                    min_price=330000,
                    max_price=340000,
                    crawl_count=2,
                ),
                Product(
                    source=SourceEnum.danawa,
                    category=CategoryEnum.memory,
                    name="오늘만 있는 데이터",
                    price=999999,
                    rank=1,
                    crawled_at=datetime(2026, 5, 13, 1, 0, tzinfo=timezone.utc),
                ),
                Product(
                    source=SourceEnum.smtcom,
                    category=CategoryEnum.memory,
                    name="삼성전자 DDR5-5600 (16GB) PC5-44800",
                    price=333000,
                    rank=None,
                    crawled_at=datetime(2026, 5, 13, 1, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        response = await trend_daily_history(
            category="memory",
            danawa_name="삼성전자 DDR5-5600 (16GB)",
            smtcom_name=None,
            days=30,
            db=session,
        )

    assert response.danawa_name == "삼성전자 DDR5-5600 (16GB)"
    assert response.smtcom_name == "삼성전자 DDR5-5600 (16GB) PC5-44800"
    assert len(response.history) == 1
    assert response.history[0].date == str(saved_day)
    assert response.history[0].danawa_price == 340000
    assert response.history[0].smtcom_price == 335000


@pytest.mark.asyncio
async def test_daily_history_includes_today_latest_products(tmp_path):
    db_path = tmp_path / "trend_today.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    target_day = date(2026, 5, 15)
    async with session_factory() as session:
        session.add_all(
            [
                DailyPrice(
                    date=date(2026, 5, 14),
                    source=SourceEnum.danawa,
                    category=CategoryEnum.memory,
                    name="삼성전자 DDR5-5600 (16GB)",
                    avg_price=340000,
                    min_price=330000,
                    max_price=350000,
                    crawl_count=2,
                ),
                Product(
                    source=SourceEnum.danawa,
                    category=CategoryEnum.memory,
                    name="삼성전자 DDR5-5600 (16GB)",
                    price=320000,
                    rank=1,
                    crawled_at=datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc),
                ),
                Product(
                    source=SourceEnum.danawa,
                    category=CategoryEnum.memory,
                    name="삼성전자 DDR5-5600 (16GB)",
                    price=330000,
                    rank=1,
                    crawled_at=datetime(2026, 5, 15, 1, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        await session.commit()

        history = await get_daily_history(
            session,
            CategoryEnum.memory,
            "삼성전자 DDR5-5600 (16GB)",
            None,
            days=30,
            today=target_day,
        )

    assert history == [
        {"date": "2026-05-14", "danawa_price": 340000, "smtcom_price": None},
        {"date": "2026-05-15", "danawa_price": 330000, "smtcom_price": None},
    ]


@pytest.mark.asyncio
async def test_daily_history_groups_memory_name_variants(tmp_path):
    db_path = tmp_path / "trend_alias.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all(
            [
                DailyPrice(
                    date=date(2026, 6, 20),
                    source=SourceEnum.danawa,
                    category=CategoryEnum.memory,
                    name="마이크론 Crucial DDR5-5600 CL46 대원씨티에스 (8GB)",
                    avg_price=170000,
                    min_price=170000,
                    max_price=170000,
                    crawl_count=1,
                ),
                DailyPrice(
                    date=date(2026, 6, 21),
                    source=SourceEnum.danawa,
                    category=CategoryEnum.memory,
                    name="마이크론 Crucial DDR5-5600 CL46 (8GB)",
                    avg_price=168000,
                    min_price=168000,
                    max_price=168000,
                    crawl_count=1,
                ),
                Product(
                    source=SourceEnum.danawa,
                    category=CategoryEnum.memory,
                    name="마이크론 Crucial DDR5-5600 CL46 대원씨티에스 (8GB)",
                    price=169000,
                    rank=1,
                    crawled_at=datetime(2026, 6, 22, 1, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        await session.commit()

        history = await get_daily_history(
            session,
            CategoryEnum.memory,
            "마이크론 Crucial DDR5-5600 CL46 대원씨티에스 (8GB)",
            None,
            days=30,
            today=date(2026, 6, 22),
        )

    assert history == [
        {"date": "2026-06-20", "danawa_price": 170000, "smtcom_price": None},
        {"date": "2026-06-21", "danawa_price": 168000, "smtcom_price": None},
        {"date": "2026-06-22", "danawa_price": 169000, "smtcom_price": None},
    ]


@pytest.mark.asyncio
async def test_one_day_history_falls_back_to_latest_saved_day(tmp_path):
    db_path = tmp_path / "trend_latest_day.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add(
            DailyPrice(
                date=date(2026, 5, 13),
                source=SourceEnum.danawa,
                category=CategoryEnum.memory,
                name="삼성전자 DDR5-5600 (16GB)",
                avg_price=357653.333,
                min_price=350000,
                max_price=360000,
                crawl_count=3,
            )
        )
        await session.commit()

        history = await get_daily_history(
            session,
            CategoryEnum.memory,
            "삼성전자 DDR5-5600 (16GB)",
            None,
            days=1,
            today=date(2026, 5, 15),
        )

    assert history == [
        {"date": "2026-05-13", "danawa_price": 357653.333, "smtcom_price": None},
    ]


@pytest.mark.asyncio
async def test_trend_products_are_sorted_by_name(tmp_path):
    db_path = tmp_path / "trend_products.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    crawled_at = datetime(2026, 5, 15, 1, 0, tzinfo=timezone.utc)
    async with session_factory() as session:
        session.add_all(
            [
                Product(
                    source=SourceEnum.danawa,
                    category=CategoryEnum.memory,
                    name="SK하이닉스 DDR5-5600 (16GB)",
                    price=50000,
                    rank=1,
                    crawled_at=crawled_at,
                ),
                Product(
                    source=SourceEnum.danawa,
                    category=CategoryEnum.memory,
                    name="삼성전자 DDR4-3200 (8GB)",
                    price=20000,
                    rank=2,
                    crawled_at=crawled_at,
                ),
                Product(
                    source=SourceEnum.danawa,
                    category=CategoryEnum.memory,
                    name="마이크론 Crucial DDR5-5600 (16GB)",
                    price=45000,
                    rank=3,
                    crawled_at=crawled_at,
                ),
            ]
        )
        await session.commit()

        products = await get_trend_products(session, CategoryEnum.memory)

    assert products == [
        "SK하이닉스 DDR5-5600 (16GB)",
        "마이크론 Crucial DDR5-5600 (16GB)",
        "삼성전자 DDR4-3200 (8GB)",
    ]
