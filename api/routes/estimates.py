from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.estimates import TARGET_CATEGORIES, crawl_estimates, fetch_posted_at_map
from api.routes.admin import admin_required
from db.crud import (
    delete_estimate_post,
    get_estimate_product_name_overrides,
    get_estimate_wr_ids_missing_posted_at,
    get_estimate_posts_by_author,
    get_estimate_stats,
    get_estimate_summary,
    get_estimate_settings,
    get_existing_estimate_wr_ids,
    save_estimate_settings,
    save_estimate_crawl_results,
    save_estimate_name_overrides,
    update_estimate_posted_at,
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


class EstimatePostLink(BaseModel):
    wr_id: int
    title: str | None
    url: str
    posted_at: datetime | None
    crawled_at: datetime | None


class EstimateAuthorPosts(BaseModel):
    author: str
    post_count: int
    posts: list[EstimatePostLink]


class EstimateSettingsPayload(BaseModel):
    names: list[str] = Field(default_factory=list)


class EstimateSettingsResponse(BaseModel):
    names: list[str]
    require_assembly: bool = True


class EstimateDeleteResponse(BaseModel):
    deleted: bool
    wr_id: int


class EstimateProductNameOverrideItem(BaseModel):
    product_name: str
    override_name: str = ""
    used_count: int


class EstimateProductNameOverridesResponse(BaseModel):
    items: list[EstimateProductNameOverrideItem]


class EstimateProductNameOverridesPayload(BaseModel):
    overrides: dict[str, str] = Field(default_factory=dict)


class EstimateProductNameOverridesSaveResponse(BaseModel):
    overrides: dict[str, str]


@router.post("/estimates/crawl", response_model=EstimateCrawlResponse)
async def crawl_estimate_posts(
    payload: EstimateCrawlRequest,
    _admin=Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    names = [name.strip() for name in payload.names if name.strip()]
    known_wr_ids = await get_existing_estimate_wr_ids(db)
    try:
        results = await crawl_estimates(
            target_names=names,
            max_pages=payload.max_pages,
            known_wr_ids=known_wr_ids,
            require_assembly=True,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"estimate crawl target request failed: {exc}") from exc
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


@router.get("/estimates/posts", response_model=list[EstimateAuthorPosts])
async def estimate_posts(
    limit: int = Query(500, ge=1, le=2000),
    _admin=Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    missing_wr_ids = await get_estimate_wr_ids_missing_posted_at(db, limit=50)
    if missing_wr_ids:
        try:
            posted_at_by_wr_id = await fetch_posted_at_map(missing_wr_ids)
            await update_estimate_posted_at(db, posted_at_by_wr_id)
        except httpx.HTTPError:
            pass
    return await get_estimate_posts_by_author(db, limit=limit)


@router.delete("/estimates/posts/{wr_id}", response_model=EstimateDeleteResponse)
async def delete_estimate_post_route(
    wr_id: int,
    _admin=Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_estimate_post(db, wr_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="estimate post not found")
    return EstimateDeleteResponse(deleted=True, wr_id=wr_id)


@router.get("/estimates/product-name-overrides", response_model=EstimateProductNameOverridesResponse)
async def estimate_product_name_overrides(
    limit: int = Query(1000, ge=1, le=5000),
    _admin=Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    items = await get_estimate_product_name_overrides(db, limit=limit)
    return EstimateProductNameOverridesResponse(
        items=[EstimateProductNameOverrideItem(**item) for item in items]
    )


@router.put("/estimates/product-name-overrides", response_model=EstimateProductNameOverridesSaveResponse)
async def update_estimate_product_name_overrides(
    payload: EstimateProductNameOverridesPayload,
    _admin=Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    overrides = await save_estimate_name_overrides(db, payload.overrides)
    return EstimateProductNameOverridesSaveResponse(overrides=overrides)


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
