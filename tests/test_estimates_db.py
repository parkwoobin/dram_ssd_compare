from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.crud import (
    delete_estimate_post,
    get_estimate_name_overrides,
    get_estimate_posts_by_author,
    get_estimate_product_name_overrides,
    get_estimate_wr_ids_missing_posted_at,
    get_estimate_stats,
    save_estimate_name_overrides,
    update_estimate_posted_at,
)
from db.models import Base, EstimateItem, EstimatePost


@pytest.mark.asyncio
async def test_estimate_stats_uses_latest_crawled_price(tmp_path):
    db_path = tmp_path / "estimates.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    old_ts = datetime(2026, 6, 30, 1, 0, tzinfo=timezone.utc)
    new_ts = datetime(2026, 6, 30, 2, 0, tzinfo=timezone.utc)

    async with session_factory() as session:
        old_post = EstimatePost(wr_id=100, url="https://example.test/100", crawled_at=old_ts)
        new_post = EstimatePost(wr_id=101, url="https://example.test/101", crawled_at=new_ts)
        session.add_all([old_post, new_post])
        await session.flush()
        session.add_all([
            EstimateItem(
                post_id=old_post.id,
                wr_id=old_post.wr_id,
                part_category="CPU",
                product_name="AMD Ryzen",
                quantity=1,
                unit_price=300000,
                total_price=300000,
                crawled_at=old_ts,
            ),
            EstimateItem(
                post_id=new_post.id,
                wr_id=new_post.wr_id,
                part_category="CPU",
                product_name="AMD Ryzen",
                quantity=1,
                unit_price=280000,
                total_price=280000,
                crawled_at=new_ts,
            ),
        ])
        await session.commit()

        stats = await get_estimate_stats(session)

    assert len(stats) == 1
    assert stats[0]["used_count"] == 2
    assert stats[0]["latest_price"] == 280000


@pytest.mark.asyncio
async def test_estimate_posted_at_backfill_helpers(tmp_path):
    db_path = tmp_path / "estimate_dates.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    crawled_at = datetime(2026, 6, 30, 1, 0, tzinfo=timezone.utc)
    posted_at = datetime(2026, 6, 28, 18, 28, tzinfo=timezone.utc)

    async with session_factory() as session:
        session.add(EstimatePost(
            wr_id=76985,
            title="견적",
            author="모루",
            url="https://example.test/76985",
            crawled_at=crawled_at,
        ))
        await session.commit()

        assert await get_estimate_wr_ids_missing_posted_at(session) == [76985]
        assert await update_estimate_posted_at(session, {76985: posted_at}) == 1
        assert await get_estimate_wr_ids_missing_posted_at(session) == []

        groups = await get_estimate_posts_by_author(session)

    assert groups[0]["posts"][0]["posted_at"] == posted_at.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_estimate_posts_by_author_orders_authors_by_latest_post(tmp_path):
    db_path = tmp_path / "estimate_author_order.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all([
            EstimatePost(
                wr_id=1,
                title="이전 견적",
                author="모루",
                url="https://example.test/1",
                posted_at=datetime(2026, 6, 28, 18, 0),
                crawled_at=datetime(2026, 6, 30, 1, 0),
            ),
            EstimatePost(
                wr_id=2,
                title="최신 견적",
                author="궁금",
                url="https://example.test/2",
                posted_at=datetime(2026, 6, 30, 12, 0),
                crawled_at=datetime(2026, 6, 30, 12, 5),
            ),
            EstimatePost(
                wr_id=3,
                title="모루 추가 견적",
                author="모루",
                url="https://example.test/3",
                posted_at=datetime(2026, 6, 29, 9, 0),
                crawled_at=datetime(2026, 6, 30, 2, 0),
            ),
        ])
        await session.commit()

        groups = await get_estimate_posts_by_author(session)

    assert [group["author"] for group in groups] == ["궁금", "모루"]
    assert [post["wr_id"] for post in groups[1]["posts"]] == [3, 1]


@pytest.mark.asyncio
async def test_delete_estimate_post_removes_items(tmp_path):
    db_path = tmp_path / "estimate_delete.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        post = EstimatePost(
            wr_id=10,
            title="삭제 대상",
            author="모루",
            url="https://example.test/10",
            crawled_at=datetime(2026, 7, 2, 1, 0),
        )
        session.add(post)
        await session.flush()
        session.add(EstimateItem(
            post_id=post.id,
            wr_id=post.wr_id,
            part_category="CPU",
            product_name="AMD Ryzen",
            quantity=1,
            unit_price=300000,
            total_price=300000,
            crawled_at=post.crawled_at,
        ))
        await session.commit()

        assert await delete_estimate_post(session, 10) is True
        assert await delete_estimate_post(session, 10) is False
        post_count = await session.scalar(select(func.count()).select_from(EstimatePost))
        item_count = await session.scalar(select(func.count()).select_from(EstimateItem))

    assert post_count == 0
    assert item_count == 0


@pytest.mark.asyncio
async def test_estimate_name_overrides_affect_stats_and_ignore_blank_values(tmp_path):
    db_path = tmp_path / "estimate_name_overrides.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    long_name = "[AMD] AMD 라이젠7-5세대 7800X3D (라파엘) (멀티팩(정품))"
    async with session_factory() as session:
        post = EstimatePost(
            wr_id=20,
            title="견적",
            author="모루",
            url="https://example.test/20",
            crawled_at=datetime(2026, 7, 2, 1, 0),
        )
        session.add(post)
        await session.flush()
        session.add(EstimateItem(
            post_id=post.id,
            wr_id=post.wr_id,
            part_category="CPU",
            product_name=long_name,
            quantity=1,
            unit_price=450000,
            total_price=450000,
            crawled_at=post.crawled_at,
        ))
        await session.commit()

        saved = await save_estimate_name_overrides(session, {
            long_name: "7800X3D",
            "blank": "",
        })
        stats = await get_estimate_stats(session)
        rows = await get_estimate_product_name_overrides(session)

    assert saved == {long_name: "7800X3D"}
    assert stats[0]["product_name"] == "7800X3D"
    assert rows[0]["product_name"] == long_name
    assert rows[0]["override_name"] == "7800X3D"

    async with session_factory() as session:
        saved = await save_estimate_name_overrides(session, {long_name: ""})
        overrides = await get_estimate_name_overrides(session)
        stats = await get_estimate_stats(session)

    assert saved == {}
    assert overrides == {}
    assert stats[0]["product_name"] == long_name
