import asyncio
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag


BOARD_URL = "https://www.smtcom.co.kr/bbs/board.php"
BOARD_TABLE = "comm_pcsangdam"
TARGET_CATEGORIES = {
    "CPU": "CPU",
    "메모리": "메모리",
    "메인보드": "메인보드",
    "그래픽카드": "그래픽 카드",
    "그래픽 카드": "그래픽 카드",
    "케이스": "케이스",
    "파워": "파워",
    "SSD": "SSD",
    "쿨러": "쿨러",
    "쿨러/튜닝": "쿨러",
}
ASSEMBLY_RE = re.compile(r"(조립\s*비|조립\s*서비스|PC\s*조립|컴퓨터\s*조립)", re.IGNORECASE)
POSTED_AT_RE = re.compile(r"작성일\s*:?\s*(\d{2,4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})")
PRICE_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)\s*원")
KST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": f"{BOARD_URL}?bo_table={BOARD_TABLE}",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _parse_int(value: str | None) -> int | None:
    nums = re.sub(r"[^\d]", "", value or "")
    return int(nums) if nums else None


def _parse_price(value: str | None) -> int | None:
    match = PRICE_RE.search(value or "")
    return _parse_int(match.group(1)) if match else None


def _clean_product_name(value: str | None) -> str:
    text = _clean_text(value)
    return re.sub(r"^\[[^\]]+\]\s*", "", text).strip()


def _wr_id_from_url(url: str) -> int | None:
    query = parse_qs(urlparse(url).query)
    raw = query.get("wr_id", [None])[0]
    return int(raw) if raw and raw.isdigit() else None


def _post_url(wr_id: int) -> str:
    return f"{BOARD_URL}?{urlencode({'bo_table': BOARD_TABLE, 'wr_id': wr_id})}"


def _extract_author(row: Tag) -> str | None:
    for selector in (".td_name", ".sv_wrap", ".name", "[headers*=name]"):
        node = row.select_one(selector)
        text = _clean_text(node.get_text(" ", strip=True) if node else "")
        if text:
            return text

    cells = row.find_all(["td", "th"])
    for cell in cells:
        text = _clean_text(cell.get_text(" ", strip=True))
        if text and len(text) <= 24 and not re.fullmatch(r"[\d./:-]+", text):
            if not cell.find("a", href=re.compile(r"wr_id=\d+")):
                return text
    return None


def parse_board_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    posts: dict[int, dict] = {}

    for link in soup.find_all("a", href=re.compile(r"wr_id=\d+")):
        href = urljoin(BOARD_URL, link.get("href", ""))
        wr_id = _wr_id_from_url(href)
        if wr_id is None:
            continue

        row = link.find_parent("tr")
        title = _clean_text(link.get_text(" ", strip=True))
        if not title:
            continue

        author = _extract_author(row) if isinstance(row, Tag) else None
        posts[wr_id] = {
            "wr_id": wr_id,
            "title": title,
            "author": author,
            "url": _post_url(wr_id),
        }

    return sorted(posts.values(), key=lambda item: item["wr_id"], reverse=True)


def _category_key(value: str) -> str | None:
    normalized = _clean_text(value).replace(" ", "")
    for raw, mapped in TARGET_CATEGORIES.items():
        if normalized == raw.replace(" ", ""):
            return mapped
    return None


def _product_name_from_cells(cells: list[Tag]) -> str | None:
    candidates = []
    for idx, cell in enumerate(cells):
        text = _clean_text(cell.get_text(" ", strip=True))
        if idx == 0 or not text:
            continue
        if re.fullmatch(r"[\d,]+원?", text) or re.fullmatch(r"\d+개", text):
            continue
        if len(text) >= 4:
            candidates.append(_clean_product_name(text))
    return max(candidates, key=len) if candidates else None


def parse_estimate_detail(html: str, wr_id: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 3:
            continue

        category = _category_key(cells[0].get_text(" ", strip=True))
        if not category:
            continue

        product_name = _product_name_from_cells(cells)
        if not product_name:
            continue

        texts = [_clean_text(cell.get_text(" ", strip=True)) for cell in cells]
        quantity = next((_parse_int(text) for text in texts if re.search(r"\d+\s*개", text)), None)
        prices = [price for text in texts if (price := _parse_price(text)) is not None]

        items.append(
            {
                "wr_id": wr_id,
                "part_category": category,
                "product_name": product_name,
                "quantity": quantity,
                "unit_price": prices[0] if prices else None,
                "total_price": prices[-1] if prices else None,
            }
        )

    return items


def parse_posted_at(html: str) -> datetime | None:
    text = _clean_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    match = POSTED_AT_RE.search(text)
    if not match:
        return None

    year, month, day, hour, minute = (int(part) for part in match.groups())
    if year < 100:
        year += 2000
    return datetime(year, month, day, hour, minute, tzinfo=KST)


async def fetch_posted_at(client: httpx.AsyncClient, wr_id: int) -> datetime | None:
    resp = await client.get(_post_url(wr_id))
    resp.raise_for_status()
    return parse_posted_at(resp.text)


async def fetch_posted_at_map(wr_ids: list[int]) -> dict[int, datetime]:
    dates: dict[int, datetime] = {}
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for wr_id in wr_ids:
            posted_at = await fetch_posted_at(client, wr_id)
            if posted_at is not None:
                dates[wr_id] = posted_at
    return dates


def has_assembly_fee(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    for row in soup.find_all("tr"):
        row_text = _clean_text(row.get_text(" ", strip=True))
        if ASSEMBLY_RE.search(row_text) and "원" in row_text:
            return True
    return False


def _matches_names(post: dict, target_names: list[str]) -> bool:
    if not target_names:
        return True
    haystack = (post.get("author") or "").casefold()
    return any(name.casefold() in haystack for name in target_names if name.strip())


def _estimate_title_key(post: dict) -> str:
    author = _clean_text(post.get("author")).casefold()
    title = _clean_text(post.get("title")).casefold()
    return f"{author}\0{title}" if title else f"wr_id:{post['wr_id']}"


def matching_posts(posts: list[dict], target_names: list[str]) -> list[dict]:
    matched = []
    seen_title_keys: set[str] = set()
    for post in sorted(posts, key=lambda item: item["wr_id"], reverse=True):
        if not _matches_names(post, target_names):
            continue
        key = _estimate_title_key(post)
        if key in seen_title_keys:
            continue
        seen_title_keys.add(key)
        matched.append(post)
    return matched


async def crawl_estimates(
    target_names: list[str] | None = None,
    max_pages: int = 3,
    known_wr_ids: set[int] | None = None,
    require_assembly: bool = False,
) -> list[dict]:
    target_names = [name.strip() for name in (target_names or []) if name.strip()]
    known_wr_ids = known_wr_ids or set()
    crawled_at = datetime.now(timezone.utc)
    results = []

    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        posts: list[dict] = []
        for page in range(1, max_pages + 1):
            params = {"bo_table": BOARD_TABLE}
            if page > 1:
                params["page"] = page
            resp = await client.get(BOARD_URL, params=params)
            resp.raise_for_status()
            posts.extend(parse_board_list(resp.text))

        seen_wr_ids: set[int] = set()
        unique_posts = []
        for post in posts:
            if post["wr_id"] in seen_wr_ids:
                continue
            seen_wr_ids.add(post["wr_id"])
            unique_posts.append(post)

        for post in matching_posts(unique_posts, target_names):
            wr_id = post["wr_id"]
            if wr_id in known_wr_ids:
                continue

            resp = await client.get(_post_url(wr_id))
            resp.raise_for_status()
            if require_assembly and not has_assembly_fee(resp.text):
                continue
            items = parse_estimate_detail(resp.text, wr_id)
            if not items:
                continue

            post["posted_at"] = parse_posted_at(resp.text)
            post["crawled_at"] = crawled_at
            results.append({"post": post, "items": items})

    return results


if __name__ == "__main__":
    async def _test():
        rows = await crawl_estimates(max_pages=1)
        print(f"{len(rows)} posts")
        for row in rows[:3]:
            print(row["post"], len(row["items"]))

    asyncio.run(_test())
