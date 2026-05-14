import re
from typing import Literal, Optional
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import CategoryEnum, SourceEnum
from db.crud import get_latest_products
from crawler.matcher import match_products, _ddr_gen, _storage_gb

router = APIRouter()

SortKey = Literal["popular", "price_asc", "price_desc"]
CategoryKey = Literal["memory", "ssd"]

_ECC_HARD = re.compile(r'\b(RDIMM|LRDIMM|Registered|서버용)\b', re.IGNORECASE)


def _is_ecc(name: str) -> bool:
    if _ECC_HARD.search(name):
        return True
    for m in re.finditer(r'ECC', name, re.IGNORECASE):
        before = name[max(0, m.start() - 3):m.start()]
        if '온다이' not in before:
            return True
    return False


def _filter_products(
    products: list[dict],
    ddr: Optional[str],
    ecc_exclude: bool,
    capacity_gb: Optional[int],
    ddr45_only: bool = False,
) -> list[dict]:
    out = []
    for p in products:
        name = p["name"]
        gen = _ddr_gen(name)

        # 메모리는 항상 DDR4/DDR5만 표시 (DDR3 이하 제외)
        if ddr45_only and gen is not None and gen not in (4, 5):
            continue

        # DDR 세대 필터 (명시적 선택 시)
        if ddr:
            if gen is not None and gen != int(ddr):
                continue

        if ecc_exclude and _is_ecc(name):
            continue
        if capacity_gb is not None:
            cap = _storage_gb(name)
            if cap is not None and cap != capacity_gb:
                continue
        out.append(p)
    return out


class PriceItem(BaseModel):
    danawa_name: str
    danawa_price: int | None
    danawa_rank: int | None
    smtcom_name: str | None
    smtcom_price: int | None
    price_diff: int | None
    match_score: float


class CompareResponse(BaseModel):
    category: str
    sort: str
    items: list[PriceItem]
    total: int
    matched: int


def _to_response(category: str, sort: str, matched_list: list[dict]) -> CompareResponse:
    items = []
    matched_count = 0

    for r in matched_list:
        dw = r["danawa"]
        smt = r["smtcom"]

        diff = None
        if smt and dw.get("price") and smt.get("price"):
            diff = smt["price"] - dw["price"]

        if smt:
            matched_count += 1

        items.append(
            PriceItem(
                danawa_name=dw["name"],
                danawa_price=dw.get("price"),
                danawa_rank=dw.get("rank"),
                smtcom_name=smt["name"] if smt else None,
                smtcom_price=smt["price"] if smt else None,
                price_diff=diff,
                match_score=r["score"],
            )
        )

    # 정렬 적용
    if sort == "popular":
        # 다나와 인기상품순 (rank 기준)
        items.sort(key=lambda x: (x.danawa_rank is None, x.danawa_rank or float('inf')))
    elif sort == "price_asc":
        items.sort(key=lambda x: (x.smtcom_price is None, x.smtcom_price or 0))
    elif sort == "price_desc":
        items.sort(key=lambda x: (x.smtcom_price is None, -(x.smtcom_price or 0)))

    return CompareResponse(
        category=category,
        sort=sort,
        items=items,
        total=len(items),
        matched=matched_count,
    )


@router.get("/compare/{category}", response_model=CompareResponse)
async def compare_prices(
    category: CategoryKey,
    sort: SortKey = Query("popular"),
    ddr: Optional[Literal["4", "5"]] = Query(None, description="DDR 세대 필터 (memory 전용)"),
    ecc_exclude: bool = Query(False, description="ECC 제품 제외 (memory 전용)"),
    capacity_gb: Optional[int] = Query(None, description="SSD 용량 필터(GB): 256/512/1024/2048/4096"),
    db: AsyncSession = Depends(get_db),
):
    cat = CategoryEnum(category)
    dw_rows = await get_latest_products(db, cat, SourceEnum.danawa)
    smt_rows = await get_latest_products(db, cat, SourceEnum.smtcom)

    dw_products = [
        {
            "name": row.name,
            "price": row.price,
            "rank": row.rank,
        }
        for row in dw_rows
    ]
    smt_products = [
        {
            "name": row.name,
            "price": row.price,
            "rank": row.rank,
        }
        for row in smt_rows
    ]

    if category == "memory":
        dw_products = _filter_products(dw_products, ddr, ecc_exclude, capacity_gb, ddr45_only=True)
        smt_products = _filter_products(smt_products, ddr, ecc_exclude, capacity_gb, ddr45_only=True)
    elif category == "ssd":
        dw_products = _filter_products(dw_products, None, False, capacity_gb)
        smt_products = _filter_products(smt_products, None, False, capacity_gb)

    matched = match_products(dw_products, smt_products, category=category)
    return _to_response(category, sort, matched)
