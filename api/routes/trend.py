from typing import Optional, Literal
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import CategoryEnum
from db.crud import get_trend_products, get_daily_history, get_saved_daily_history, get_smtcom_product_names
from crawler.matcher import _normalize, _storage_gb, _extract_brand, _ddr_gen, MATCH_THRESHOLD
from rapidfuzz import fuzz

router = APIRouter()


class TrendProductsResponse(BaseModel):
    category: str
    products: list[str]


class TrendPoint(BaseModel):
    date: str
    danawa_price: float | None
    smtcom_price: float | None


class TrendHistoryResponse(BaseModel):
    danawa_name: str
    smtcom_name: str | None
    history: list[TrendPoint]
    category: str


def _find_best_smtcom(danawa_name: str, smtcom_names: list[str]) -> str | None:
    dw_cap = _storage_gb(danawa_name)
    dw_brand = _extract_brand(danawa_name)
    dw_ddr = _ddr_gen(danawa_name)
    dw_norm = _normalize(danawa_name)

    best_score = 0.0
    best_name = None
    for smt_name in smtcom_names:
        if dw_cap and _storage_gb(smt_name) and dw_cap != _storage_gb(smt_name):
            continue
        if dw_brand and _extract_brand(smt_name) and dw_brand != _extract_brand(smt_name):
            continue
        if dw_ddr and _ddr_gen(smt_name) and dw_ddr != _ddr_gen(smt_name):
            continue
        score = fuzz.WRatio(dw_norm, _normalize(smt_name))
        if score > best_score:
            best_score = score
            best_name = smt_name

    return best_name if best_score >= MATCH_THRESHOLD else None


@router.get("/trend/products", response_model=TrendProductsResponse)
async def trend_products(
    category: Literal["memory", "ssd"] = Query(...),
    db: AsyncSession = Depends(get_db),
):
    cat = CategoryEnum(category)
    products = await get_trend_products(db, cat)
    return TrendProductsResponse(category=category, products=products)


@router.get("/trend/history", response_model=TrendHistoryResponse)
async def trend_history(
    category: Literal["memory", "ssd"] = Query(...),
    danawa_name: str = Query(...),
    smtcom_name: Optional[str] = Query(None),
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
):
    cat = CategoryEnum(category)

    resolved_smtcom = smtcom_name
    if not resolved_smtcom:
        smt_names = await get_smtcom_product_names(db, cat)
        resolved_smtcom = _find_best_smtcom(danawa_name, smt_names)

    history_rows = await get_daily_history(db, cat, danawa_name, resolved_smtcom, days)
    history = [TrendPoint(**r) for r in history_rows]

    return TrendHistoryResponse(
        danawa_name=danawa_name,
        smtcom_name=resolved_smtcom,
        history=history,
        category=category,
    )


@router.get("/trend/daily-history", response_model=TrendHistoryResponse)
async def trend_daily_history(
    category: Literal["memory", "ssd"] = Query(...),
    danawa_name: str = Query(...),
    smtcom_name: Optional[str] = Query(None),
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
):
    cat = CategoryEnum(category)

    resolved_smtcom = smtcom_name
    if not resolved_smtcom:
        smt_names = await get_smtcom_product_names(db, cat)
        resolved_smtcom = _find_best_smtcom(danawa_name, smt_names)

    # 저장된 데이터 + 오늘 실시간 데이터 포함
    history_rows = await get_daily_history(db, cat, danawa_name, resolved_smtcom, days)
    history = [TrendPoint(**r) for r in history_rows]

    return TrendHistoryResponse(
        danawa_name=danawa_name,
        smtcom_name=resolved_smtcom,
        history=history,
        category=category,
    )


@router.get("/trend/test-debug", response_model=TrendHistoryResponse)
async def trend_test_debug(
    category: Literal["memory", "ssd"] = Query("memory"),
):
    """디버그용 테스트 데이터 - 차트 미리보기용"""
    from datetime import datetime, timedelta
    
    base_date = datetime.now().date() - timedelta(days=29)
    history = []
    
    for i in range(30):
        current_date = base_date + timedelta(days=i)
        # 가격 변동 시뮬레이션 (삼각파)
        danawa_price = 350000 - int(5000 * (1 - (i / 30))) + int(10000 * abs((i % 10) - 5) / 5)
        smtcom_price = danawa_price - 5000 + int(3000 * (i % 5))
        
        history.append(
            TrendPoint(
                date=str(current_date),
                danawa_price=danawa_price if danawa_price > 0 else None,
                smtcom_price=smtcom_price if smtcom_price > 0 else None,
            )
        )
    
    product_name = "삼성전자 DDR5-5600 (16GB)" if category == "memory" else "삼성 990 PRO (1TB)"
    
    return TrendHistoryResponse(
        danawa_name=product_name,
        smtcom_name="삼성전자 DDR5-5600 (16GB) PC5-44800" if category == "memory" else "삼성 990 PRO NVMe 1TB",
        history=history,
        category=category,
    )
