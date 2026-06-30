from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.crud import get_estimate_stats
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
