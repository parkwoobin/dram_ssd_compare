import sqlite3
from datetime import date

from sqlalchemy import create_engine

from db.models import Base
from scripts.fill_daily_price_gaps import fill_daily_price_gaps


def test_fill_daily_price_gaps_copies_previous_price(tmp_path):
    db_path = tmp_path / "prices.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    con = sqlite3.connect(db_path)
    try:
        con.execute("""
            insert into daily_prices
                (date, source, category, name, avg_price, min_price, max_price, crawl_count)
            values (?, ?, ?, ?, ?, ?, ?, ?)
        """, (date(2026, 6, 20).isoformat(), "danawa", "ssd", "삼성전자 990 PRO M.2 NVMe (4TB)", 1539000, 1539000, 1539000, 1))
        con.execute("""
            insert into daily_prices
                (date, source, category, name, avg_price, min_price, max_price, crawl_count)
            values (?, ?, ?, ?, ?, ?, ?, ?)
        """, (date(2026, 6, 22).isoformat(), "danawa", "ssd", "삼성전자 990 PRO M.2 NVMe (4TB)", 1426100, 1426100, 1426100, 1))
        con.commit()
    finally:
        con.close()

    inserted = fill_daily_price_gaps(db_path)

    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("""
            select date, avg_price, min_price, max_price, crawl_count
            from daily_prices
            order by date
        """).fetchall()
    finally:
        con.close()

    assert inserted == 1
    assert rows == [
        ("2026-06-20", 1539000.0, 1539000, 1539000, 1),
        ("2026-06-21", 1539000.0, 1539000, 1539000, 0),
        ("2026-06-22", 1426100.0, 1426100, 1426100, 1),
    ]
