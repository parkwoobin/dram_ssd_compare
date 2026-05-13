import asyncio
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import httpx

SMTCOM_BASE = (
    "https://www.smtcom.co.kr/skin/shop/basic/estimate_search_new2.php"
    "?depth=2&cate1=17&cate2={cate2}&cate3=&cate4=&list_num=9999&sort={sort}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.smtcom.co.kr/shop/estimatepc.html",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

CATEGORIES = {
    "memory": "19",
    "ssd": "28",
}

SORT_KEYS = {
    "popular": "popular",
    "newest": "new",
    "price_asc": "cheap",
    "price_desc": "expensive",
}


def _parse_price(text: str) -> int | None:
    nums = re.sub(r"[^\d]", "", text)
    return int(nums) if nums else None


def _parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen_ids: set[str] = set()

    # 전체 product_detail_db 링크를 기준으로 제품 추출
    for name_el in soup.find_all("a", href=re.compile(r"product_detail_db\.html\?pd_no=\d+")):
        name = name_el.get_text(strip=True)
        if not name:
            continue

        m = re.search(r"pd_no=(\d+)", name_el.get("href", ""))
        prod_id = m.group(1) if m else None
        if prod_id in seen_ids:
            continue
        seen_ids.add(prod_id or name)

        # 가장 가까운 상위 컨테이너에서 가격 탐색
        container = name_el.parent
        price = None
        for _ in range(8):
            if container is None:
                break
            price_el = container.find(class_="OPP_price")
            if price_el:
                price = _parse_price(price_el.get_text())
                break
            # insertProduct onclick 에서 가격 파싱 (fallback)
            insert_el = container.find("a", href=re.compile(r"insertProduct"))
            if insert_el:
                m2 = re.search(r"insertProduct\('[^']+','[^']+','[^']+','[^']+','(\d+)'\)", insert_el.get("href", ""))
                if m2:
                    price = int(m2.group(1))
                    break
            container = container.parent

        products.append(
            {
                "smtcom_id": prod_id,
                "name": name,
                "price": price,
                "crawled_at": datetime.now(timezone.utc),
            }
        )

    return products


async def crawl(category: str, sort: str = "popular") -> list[dict]:
    cate2 = CATEGORIES[category]
    sort_param = SORT_KEYS.get(sort, SORT_KEYS["popular"])
    url = SMTCOM_BASE.format(cate2=cate2, sort=sort_param)

    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return _parse_html(resp.text)
        except Exception as e:
            print(f"[Smtcom] 크롤링 오류: {e}")
            return []


if __name__ == "__main__":
    async def _test():
        for cat in ("memory", "ssd"):
            products = await crawl(cat)
            print(f"[스마트컴] {cat}: {len(products)}개")
            for p in products[:5]:
                print(f"  {p['name']} | {p['price']}원")

    asyncio.run(_test())
