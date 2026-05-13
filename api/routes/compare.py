import asyncio
from typing import Literal
from fastapi import APIRouter, Query
from pydantic import BaseModel

from crawler.danawa import crawl as danawa_crawl
from crawler.smtcom import crawl as smtcom_crawl
from crawler.matcher import match_products

router = APIRouter()

SortKey = Literal["popular", "newest", "price_asc", "price_desc"]
CategoryKey = Literal["memory", "ssd"]


class PriceItem(BaseModel):
    danawa_name: str
    danawa_price: int | None
    danawa_rank: int | None
    smtcom_name: str | None
    smtcom_price: int | None
    price_diff: int | None       # smtcom - danawa (양수=스마트컴 비쌈, 음수=스마트컴 저렴)
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

    # 정렬 재적용 (smtcom 가격 기준 정렬)
    if sort == "price_asc":
        items.sort(key=lambda x: (x.smtcom_price is None, x.smtcom_price or 0))
    elif sort == "price_desc":
        items.sort(key=lambda x: (x.smtcom_price is None, -(x.smtcom_price or 0)))
    elif sort == "newest":
        pass  # 신상품순은 danawa 기준 순서 유지
    # popular: danawa rank 순서 유지

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
    sort: SortKey = Query("popular", description="정렬: popular/newest/price_asc/price_desc"),
):
    dw_products, smt_products = await asyncio.gather(
        danawa_crawl(category, sort),
        smtcom_crawl(category, sort),
    )
    matched = match_products(dw_products, smt_products)
    return _to_response(category, sort, matched)
