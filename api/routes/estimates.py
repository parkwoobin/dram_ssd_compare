from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.estimates import TARGET_CATEGORIES, crawl_estimates
from api.routes.admin import admin_required
from db.crud import (
    get_estimate_stats,
    get_estimate_summary,
    get_estimate_settings,
    get_existing_estimate_wr_ids,
    save_estimate_settings,
    save_estimate_crawl_results,
)
from db.database import get_db


router = APIRouter()

EstimateSort = Literal["count_desc", "count_asc", "name_asc", "name_desc"]


class EstimateCrawlRequest(BaseModel):
    names: list[str] = Field(default_factory=list)
    max_pages: int = Field(default=3, ge=1, le=20)


class EstimateCrawlResponse(BaseModel):
    crawled_posts: int
    saved_posts: int
    target_names: list[str]


class EstimateStatItem(BaseModel):
    part_category: str
    product_name: str
    latest_price: int | None
    latest_total_price: int | None
    latest_crawled_at: datetime | None
    used_count: int
    quantity_count: int


class EstimateStatsResponse(BaseModel):
    summary: dict
    categories: list[str]
    items: list[EstimateStatItem]


class EstimateSettingsPayload(BaseModel):
    names: list[str] = Field(default_factory=list)


class EstimateSettingsResponse(BaseModel):
    names: list[str]
    require_assembly: bool = True


@router.post("/estimates/crawl", response_model=EstimateCrawlResponse)
async def crawl_estimate_posts(
    payload: EstimateCrawlRequest,
    _admin=Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    names = [name.strip() for name in payload.names if name.strip()]
    known_wr_ids = await get_existing_estimate_wr_ids(db)
    results = await crawl_estimates(
        target_names=names,
        max_pages=payload.max_pages,
        known_wr_ids=known_wr_ids,
        require_assembly=True,
    )
    saved = await save_estimate_crawl_results(db, results)
    return EstimateCrawlResponse(
        crawled_posts=len(results),
        saved_posts=saved,
        target_names=names,
    )


@router.get("/estimates/stats", response_model=EstimateStatsResponse)
async def estimate_stats(
    part_category: str | None = Query(None),
    sort: EstimateSort = Query("count_desc"),
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
):
    rows = await get_estimate_stats(db, part_category=part_category, sort=sort, limit=limit)
    summary = await get_estimate_summary(db)
    if isinstance(summary.get("latest_crawled_at"), datetime):
        summary["latest_crawled_at"] = summary["latest_crawled_at"].isoformat()
    return EstimateStatsResponse(
        summary=summary,
        categories=list(dict.fromkeys(TARGET_CATEGORIES.values())),
        items=[EstimateStatItem(**row) for row in rows],
    )


@router.get("/estimates/settings", response_model=EstimateSettingsResponse)
async def estimate_settings(
    _admin=Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    settings = await get_estimate_settings(db)
    return EstimateSettingsResponse(names=settings["names"], require_assembly=True)


@router.put("/estimates/settings", response_model=EstimateSettingsResponse)
async def update_estimate_settings(
    payload: EstimateSettingsPayload,
    _admin=Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    settings = await save_estimate_settings(db, payload.names)
    return EstimateSettingsResponse(names=settings["names"], require_assembly=True)
