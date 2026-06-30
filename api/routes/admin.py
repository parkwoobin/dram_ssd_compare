import json
import hmac
import hashlib
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import AppSetting, CategoryEnum, Product, SourceEnum


router = APIRouter()
BASE_DIR = Path(__file__).resolve().parents[2]
MARK_HTML_PATH = BASE_DIR / "HTML" / "3DMark_260628_embed.html"
TREND_DEFAULTS_KEY = "trend_defaults"
ADMIN_COOKIE_NAME = "admin_session"
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "smtadmin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "smt123")
ADMIN_SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET", "dram-ssd-admin-session")


class AdminProductItem(BaseModel):
    id: int
    source: str
    category: str
    name: str
    price: int | None
    rank: int | None
    crawled_at: str


class AdminProductUpdate(BaseModel):
    name: str
    price: int | None = None
    rank: int | None = None


class TrendDefaults(BaseModel):
    memory: str = ""
    ssd: str = ""


class HtmlPayload(BaseModel):
    html: str


class AdminLoginPayload(BaseModel):
    username: str
    password: str


def _admin_token() -> str:
    return hmac.new(
        ADMIN_SESSION_SECRET.encode("utf-8"),
        ADMIN_USERNAME.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def is_admin_request(request: Request) -> bool:
    token = request.cookies.get(ADMIN_COOKIE_NAME, "")
    return hmac.compare_digest(token, _admin_token())


async def admin_required(request: Request):
    if not is_admin_request(request):
        raise HTTPException(status_code=401, detail="admin login required")


@router.post("/admin/login")
async def admin_login(payload: AdminLoginPayload, response: Response):
    if not (
        hmac.compare_digest(payload.username, ADMIN_USERNAME)
        and hmac.compare_digest(payload.password, ADMIN_PASSWORD)
    ):
        raise HTTPException(status_code=401, detail="invalid admin credentials")
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=_admin_token(),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24,
    )
    return {"status": "ok"}


@router.post("/admin/logout")
async def admin_logout(response: Response):
    response.delete_cookie(ADMIN_COOKIE_NAME)
    return {"status": "ok"}


@router.get("/admin/products", response_model=list[AdminProductItem])
async def admin_products(
    category: Literal["memory", "ssd"] = Query(...),
    source: Literal["danawa", "smtcom"] = Query("danawa"),
    limit: int = Query(200, ge=1, le=1000),
    _admin=Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    cat = CategoryEnum(category)
    src = SourceEnum(source)
    latest = (
        select(Product.crawled_at)
        .where(Product.category == cat, Product.source == src)
        .order_by(Product.crawled_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    result = await db.execute(
        select(Product)
        .where(Product.category == cat, Product.source == src, Product.crawled_at == latest)
        .order_by(Product.rank.asc().nullslast(), Product.id.asc())
        .limit(limit)
    )
    return [
        AdminProductItem(
            id=row.id,
            source=row.source.value,
            category=row.category.value,
            name=row.name,
            price=row.price,
            rank=row.rank,
            crawled_at=row.crawled_at.isoformat(),
        )
        for row in result.scalars().all()
    ]


@router.put("/admin/products/{product_id}", response_model=AdminProductItem)
async def update_admin_product(
    product_id: int,
    payload: AdminProductUpdate,
    _admin=Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(Product, product_id)
    if row is None:
        raise HTTPException(status_code=404, detail="product not found")
    row.name = payload.name.strip()
    row.price = payload.price
    row.rank = payload.rank
    await db.commit()
    await db.refresh(row)
    return AdminProductItem(
        id=row.id,
        source=row.source.value,
        category=row.category.value,
        name=row.name,
        price=row.price,
        rank=row.rank,
        crawled_at=row.crawled_at.isoformat(),
    )


async def _read_json_setting(db: AsyncSession, key: str, default: dict) -> dict:
    result = await db.execute(select(AppSetting).where(AppSetting.setting_key == key))
    setting = result.scalar_one_or_none()
    if not setting:
        return default
    try:
        value = json.loads(setting.setting_value)
    except json.JSONDecodeError:
        return default
    return value if isinstance(value, dict) else default


async def _write_json_setting(db: AsyncSession, key: str, value: dict) -> None:
    result = await db.execute(select(AppSetting).where(AppSetting.setting_key == key))
    setting = result.scalar_one_or_none()
    payload = json.dumps(value, ensure_ascii=False)
    if setting:
        setting.setting_value = payload
    else:
        db.add(AppSetting(setting_key=key, setting_value=payload))
    await db.commit()


@router.get("/admin/trend-defaults", response_model=TrendDefaults)
async def get_trend_defaults(db: AsyncSession = Depends(get_db)):
    data = await _read_json_setting(db, TREND_DEFAULTS_KEY, {"memory": "", "ssd": ""})
    return TrendDefaults(memory=str(data.get("memory") or ""), ssd=str(data.get("ssd") or ""))


@router.put("/admin/trend-defaults", response_model=TrendDefaults)
async def save_trend_defaults(
    payload: TrendDefaults,
    _admin=Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    data = {"memory": payload.memory.strip(), "ssd": payload.ssd.strip()}
    await _write_json_setting(db, TREND_DEFAULTS_KEY, data)
    return TrendDefaults(**data)


@router.get("/admin/3dmark-html")
async def get_3dmark_html(_admin=Depends(admin_required)):
    return {"html": MARK_HTML_PATH.read_text(encoding="utf-8")}


@router.put("/admin/3dmark-html")
async def save_3dmark_html(payload: HtmlPayload, _admin=Depends(admin_required)):
    MARK_HTML_PATH.write_text(payload.html, encoding="utf-8")
    return {"status": "ok", "bytes": len(payload.html.encode("utf-8"))}
