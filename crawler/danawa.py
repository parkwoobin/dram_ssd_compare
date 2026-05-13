import asyncio
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import httpx

DANAWA_BASE = (
    "https://shop.danawa.com/virtualestimate/"
    "?controller=estimateMain&methods=product"
    "&marketPlaceSeq=16&categorySeq={cat_seq}&categoryDepth=2&pseq=2"
    "&orderby={orderby}&page={page}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": (
        "https://shop.danawa.com/virtualestimate/"
        "?controller=estimateMain&methods=index&marketPlaceSeq=16"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

CATEGORIES = {
    "memory": 874,
    "ssd": 32617,
}

SORT_KEYS = {
    "popular": "PRODUCT_POPULAR_DESC",
    "newest": "PRODUCT_INPUT_DATE_DESC",
    "price_asc": "GOODSINFO_CASH_PRICE_ASC",
    "price_desc": "GOODSINFO_CASH_PRICE_DESC",
}

PAGES_TO_FETCH = {
    "memory": 14,  # 페이지당 ~30개, 총 ~420개 — 24GB 단품 포함 전 용량 커버 (병렬 요청)
    "ssd": 2,      # 총 ~63개 제품
}


def _parse_price(text: str) -> int | None:
    nums = re.sub(r"[^\d]", "", text)
    return int(nums) if nums else None


def _parse_page(html: str, base_rank: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select('tr[class*="productList_"]')
    products = []
    rank = base_rank

    for row in rows:
        classes = " ".join(row.get("class", []))
        if "recom_area" in classes:
            continue  # 상단 추천 제품 제외 (랭킹 대상 아님)

        # 제품 ID
        m = re.search(r"productList_(\d+)", classes)
        prod_id = m.group(1) if m else None

        # 제품명
        name_el = row.select_one("p.subject a")
        name = name_el.get_text(strip=True) if name_el else None

        # 가격
        price_el = row.select_one("p.low_price span.prod_price")
        price = _parse_price(price_el.get_text()) if price_el else None

        if name:
            products.append(
                {
                    "danawa_id": prod_id,
                    "name": name,
                    "price": price,
                    "rank": rank,
                    "crawled_at": datetime.now(timezone.utc),
                }
            )
            rank += 1

    return products


async def crawl(category: str, sort: str = "popular") -> list[dict]:
    cat_seq = CATEGORIES[category]
    orderby = SORT_KEYS.get(sort, SORT_KEYS["popular"])
    pages = PAGES_TO_FETCH.get(category, 2)

    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        async def _fetch(page: int) -> list[dict]:
            url = DANAWA_BASE.format(cat_seq=cat_seq, orderby=orderby, page=page)
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return _parse_page(resp.text, (page - 1) * 30 + 1)
            except Exception as e:
                print(f"[Danawa] 크롤링 오류 page={page}: {e}")
                return []

        results = await asyncio.gather(*[_fetch(p) for p in range(1, pages + 1)])

    all_products: list[dict] = []
    for page_products in results:
        all_products.extend(page_products)
    return all_products


if __name__ == "__main__":
    async def _test():
        for cat in ("memory", "ssd"):
            products = await crawl(cat)
            print(f"[다나와] {cat}: {len(products)}개")
            for p in products[:3]:
                print(f"  [{p['rank']}] {p['name']} | {p['price']}원")

    asyncio.run(_test())
