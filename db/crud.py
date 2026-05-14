from datetime import datetime, timezone, timedelta, date as date_type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, asc, delete, or_
from db.models import Product, CrawlLog, DailyPrice, SourceEnum, CategoryEnum


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
        ).order_by(Product.rank.asc().nullslast(), Product.id.asc())
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


async def aggregate_daily_prices(
    session: AsyncSession,
    target_date: date_type | None = None,
) -> int:
    """target_date(KST)의 hourly 데이터를 집계하여 daily_prices에 저장. 저장/갱신 레코드 수 반환."""
    if target_date is None:
        target_date = (datetime.now(timezone.utc) + timedelta(hours=9)).date()

    # KST day → UTC range
    day_start_utc = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0) - timedelta(hours=9)
    day_end_utc = day_start_utc + timedelta(days=1)

    total = 0
    for source in SourceEnum:
        for category in CategoryEnum:
            result = await session.execute(
                select(
                    Product.name,
                    func.avg(Product.price).label("avg_price"),
                    func.min(Product.price).label("min_price"),
                    func.max(Product.price).label("max_price"),
                    func.count(Product.id).label("cnt"),
                )
                .where(
                    Product.source == source,
                    Product.category == category,
                    Product.price.isnot(None),
                    Product.crawled_at >= day_start_utc,
                    Product.crawled_at < day_end_utc,
                )
                .group_by(Product.name)
            )
            for row in result.all():
                existing = await session.execute(
                    select(DailyPrice).where(
                        DailyPrice.date == target_date,
                        DailyPrice.source == source,
                        DailyPrice.name == row.name,
                    )
                )
                dp = existing.scalar_one_or_none()
                if dp:
                    dp.avg_price = row.avg_price
                    dp.min_price = row.min_price
                    dp.max_price = row.max_price
                    dp.crawl_count = row.cnt
                else:
                    session.add(DailyPrice(
                        date=target_date,
                        source=source,
                        category=category,
                        name=row.name,
                        avg_price=row.avg_price,
                        min_price=row.min_price,
                        max_price=row.max_price,
                        crawl_count=row.cnt,
                    ))
                    total += 1

    await session.commit()
    return total


async def seed_daily_prices_from_previous_day(
    session: AsyncSession,
    target_date: date_type | None = None,
) -> int:
    """target_date(KST)에 전날 daily_prices를 복사해 자정 기준 가격을 채운다."""
    if target_date is None:
        target_date = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
    source_date = target_date - timedelta(days=1)

    result = await session.execute(
        select(DailyPrice).where(DailyPrice.date == source_date)
    )
    previous_rows = result.scalars().all()

    copied = 0
    for row in previous_rows:
        existing = await session.execute(
            select(DailyPrice).where(
                DailyPrice.date == target_date,
                DailyPrice.source == row.source,
                DailyPrice.name == row.name,
            )
        )
        dp = existing.scalar_one_or_none()
        if dp and dp.crawl_count != 0:
            continue

        if dp:
            dp.category = row.category
            dp.avg_price = row.avg_price
            dp.min_price = row.min_price
            dp.max_price = row.max_price
            dp.crawl_count = 0
        else:
            session.add(DailyPrice(
                date=target_date,
                source=row.source,
                category=row.category,
                name=row.name,
                avg_price=row.avg_price,
                min_price=row.min_price,
                max_price=row.max_price,
                crawl_count=0,
            ))
        copied += 1

    await session.commit()
    return copied


async def prune_old_products(
    session: AsyncSession,
    retention_days: int = 7,
    now: datetime | None = None,
) -> int:
    """최근 retention_days일 원본 products만 보관하고 이전 원본은 삭제."""
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    if now is None:
        now = datetime.now(timezone.utc)

    cutoff = now - timedelta(days=retention_days)
    result = await session.execute(
        delete(Product).where(Product.crawled_at < cutoff)
    )
    await session.commit()
    return result.rowcount or 0


async def _get_today_latest_price(
    session: AsyncSession,
    source: SourceEnum,
    category: CategoryEnum,
    name: str,
    today: date_type,
) -> int | None:
    """오늘 Product 테이블에서 가장 최근 수집 가격 반환."""
    day_start_utc = datetime(today.year, today.month, today.day, 0, 0, 0) - timedelta(hours=9)
    day_end_utc = day_start_utc + timedelta(days=1)
    result = await session.execute(
        select(Product.price)
        .where(
            Product.source == source,
            Product.category == category,
            Product.name == name,
            Product.price.isnot(None),
            Product.crawled_at >= day_start_utc,
            Product.crawled_at < day_end_utc,
        )
        .order_by(Product.crawled_at.desc(), Product.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_daily_history(
    session: AsyncSession,
    category: CategoryEnum,
    danawa_name: str,
    smtcom_name: str | None,
    days: int = 30,
    today: date_type | None = None,
) -> list[dict]:
    """일별 평균 가격 기록 반환 (날짜 오름차순). 오늘은 Product 테이블 실시간 집계 포함."""
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
    cutoff = today - timedelta(days=max(days - 1, 0))
    today_str = str(today)

    dw_result = await session.execute(
        select(DailyPrice.date, DailyPrice.avg_price)
        .where(
            DailyPrice.source == SourceEnum.danawa,
            DailyPrice.category == category,
            DailyPrice.name == danawa_name,
            DailyPrice.date >= cutoff,
        )
        .order_by(DailyPrice.date)
    )
    dw_rows = {str(r.date): r.avg_price for r in dw_result.all()}

    smt_rows: dict = {}
    if smtcom_name:
        smt_result = await session.execute(
            select(DailyPrice.date, DailyPrice.avg_price)
            .where(
                DailyPrice.source == SourceEnum.smtcom,
                DailyPrice.category == category,
                DailyPrice.name == smtcom_name,
                DailyPrice.date >= cutoff,
            )
            .order_by(DailyPrice.date)
        )
        smt_rows = {str(r.date): r.avg_price for r in smt_result.all()}

    # 오늘은 18:05 확정 집계 전에도 시간별 products 원본으로 차트에 반영한다.
    # 오늘 DailyPrice가 이미 있어도, 장중에는 더 최신 평균으로 덮어쓴다.
    price = await _get_today_latest_price(session, SourceEnum.danawa, category, danawa_name, today)
    if price is not None:
        dw_rows[today_str] = price

    if smtcom_name:
        price = await _get_today_latest_price(session, SourceEnum.smtcom, category, smtcom_name, today)
        if price is not None:
            smt_rows[today_str] = price

    all_dates = sorted(set(dw_rows) | set(smt_rows))
    if not all_dates and days == 1:
        latest_conditions = [
            (DailyPrice.source == SourceEnum.danawa) & (DailyPrice.name == danawa_name)
        ]
        if smtcom_name:
            latest_conditions.append(
                (DailyPrice.source == SourceEnum.smtcom) & (DailyPrice.name == smtcom_name)
            )

        latest_result = await session.execute(
            select(func.max(DailyPrice.date))
            .where(
                DailyPrice.category == category,
                DailyPrice.date <= today,
                or_(*latest_conditions),
            )
        )
        latest_date = latest_result.scalar()
        if latest_date is not None:
            dw_result = await session.execute(
                select(DailyPrice.avg_price)
                .where(
                    DailyPrice.source == SourceEnum.danawa,
                    DailyPrice.category == category,
                    DailyPrice.name == danawa_name,
                    DailyPrice.date == latest_date,
                )
            )
            dw_price = dw_result.scalar()

            smt_price = None
            if smtcom_name:
                smt_result = await session.execute(
                    select(DailyPrice.avg_price)
                    .where(
                        DailyPrice.source == SourceEnum.smtcom,
                        DailyPrice.category == category,
                        DailyPrice.name == smtcom_name,
                        DailyPrice.date == latest_date,
                    )
                )
                smt_price = smt_result.scalar()

            return [
                {
                    "date": str(latest_date),
                    "danawa_price": dw_price,
                    "smtcom_price": smt_price,
                }
            ]

    return [
        {
            "date": d,
            "danawa_price": dw_rows.get(d),
            "smtcom_price": smt_rows.get(d),
        }
        for d in all_dates
    ]


async def get_saved_daily_history(
    session: AsyncSession,
    category: CategoryEnum,
    danawa_name: str,
    smtcom_name: str | None,
    days: int = 30,
) -> list[dict]:
    """daily_prices에 저장된 일별 평균 가격만 반환 (실시간 fallback 없음)."""
    now_kst = datetime.now(timezone.utc) + timedelta(hours=9)
    today = now_kst.date()
    cutoff = today - timedelta(days=max(days - 1, 0))

    dw_result = await session.execute(
        select(DailyPrice.date, DailyPrice.avg_price)
        .where(
            DailyPrice.source == SourceEnum.danawa,
            DailyPrice.category == category,
            DailyPrice.name == danawa_name,
            DailyPrice.date >= cutoff,
        )
        .order_by(DailyPrice.date)
    )
    dw_rows = {str(r.date): r.avg_price for r in dw_result.all()}

    smt_rows: dict = {}
    if smtcom_name:
        smt_result = await session.execute(
            select(DailyPrice.date, DailyPrice.avg_price)
            .where(
                DailyPrice.source == SourceEnum.smtcom,
                DailyPrice.category == category,
                DailyPrice.name == smtcom_name,
                DailyPrice.date >= cutoff,
            )
            .order_by(DailyPrice.date)
        )
        smt_rows = {str(r.date): r.avg_price for r in smt_result.all()}

    all_dates = sorted(set(dw_rows) | set(smt_rows))
    return [
        {
            "date": d,
            "danawa_price": dw_rows.get(d),
            "smtcom_price": smt_rows.get(d),
        }
        for d in all_dates
    ]


async def get_trend_products(
    session: AsyncSession,
    category: CategoryEnum,
) -> list[str]:
    """다나와 최신 크롤 제품명 목록 (추세 드롭다운용)."""
    subq = (
        select(func.max(Product.crawled_at))
        .where(
            Product.source == SourceEnum.danawa,
            Product.category == category,
        )
        .scalar_subquery()
    )
    result = await session.execute(
        select(Product.name, Product.rank)
        .where(
            Product.source == SourceEnum.danawa,
            Product.category == category,
            Product.crawled_at == subq,
        )
    )
    rows = result.all()
    rows_sorted = sorted(rows, key=lambda r: (r.rank is None, r.rank or 9999))
    return [r.name for r in rows_sorted]


async def get_smtcom_product_names(
    session: AsyncSession,
    category: CategoryEnum,
) -> list[str]:
    """스마트컴 최신 크롤 제품명 목록."""
    subq = (
        select(func.max(Product.crawled_at))
        .where(
            Product.source == SourceEnum.smtcom,
            Product.category == category,
        )
        .scalar_subquery()
    )
    result = await session.execute(
        select(Product.name)
        .where(
            Product.source == SourceEnum.smtcom,
            Product.category == category,
            Product.crawled_at == subq,
        )
    )
    return [r[0] for r in result.all()]
