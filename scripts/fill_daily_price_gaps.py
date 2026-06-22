import argparse
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path


def _default_db_path() -> Path:
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/prices.db")
    prefix = "sqlite+aiosqlite:///"
    if database_url.startswith(prefix):
        return Path(database_url[len(prefix):])
    return Path("./data/prices.db")


def _backup_database(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"prices-before-fill-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"

    source = sqlite3.connect(db_path)
    try:
        dest = sqlite3.connect(backup_path)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()

    return backup_path


def fill_daily_price_gaps(db_path: Path) -> int:
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        groups = cur.execute("""
            select source, category, name, min(date), max(date)
            from daily_prices
            where avg_price is not null
            group by source, category, name
        """).fetchall()

        inserted = 0
        for source, category, name, min_date, max_date in groups:
            rows = cur.execute("""
                select date, avg_price, min_price, max_price
                from daily_prices
                where source = ? and category = ? and name = ?
                order by date
            """, (source, category, name)).fetchall()

            by_date = {row[0]: row[1:] for row in rows}
            current = date.fromisoformat(min_date)
            end = date.fromisoformat(max_date)
            last_prices = None

            while current <= end:
                day = current.isoformat()
                if day in by_date:
                    last_prices = by_date[day]
                elif last_prices is not None:
                    avg_price, min_price, max_price = last_prices
                    cur.execute("""
                        insert or ignore into daily_prices
                            (date, source, category, name, avg_price, min_price, max_price, crawl_count)
                        values (?, ?, ?, ?, ?, ?, ?, 0)
                    """, (day, source, category, name, avg_price, min_price, max_price))
                    inserted += cur.rowcount
                current += timedelta(days=1)

        con.commit()
        return inserted
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill missing daily_prices dates with the previous known price.")
    parser.add_argument("--db-path", type=Path, default=_default_db_path())
    parser.add_argument("--backup-dir", type=Path, default=Path("./data/backups"))
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    db_path = args.db_path
    if not db_path.exists():
        raise SystemExit(f"DB file not found: {db_path}")

    backup_path = None
    if not args.no_backup:
        backup_path = _backup_database(db_path, args.backup_dir)

    inserted = fill_daily_price_gaps(db_path)
    print(f"inserted={inserted}")
    if backup_path is not None:
        print(f"backup={backup_path}")


if __name__ == "__main__":
    main()
