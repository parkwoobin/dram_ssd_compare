"""
다나와 제품명 기준으로 스마트컴 제품을 퍼지 매칭.

매칭 전략:
1. 제품명 정규화 (소문자, 특수문자 제거, 용량/규격 토큰 추출)
2. rapidfuzz WRatio 스코어 기반 유사도 계산
3. 임계값(MATCH_THRESHOLD) 이상이면 매칭, 미만이면 None
"""
import re
from rapidfuzz import fuzz

MATCH_THRESHOLD = 82  # 용량·브랜드 필터 통과 후 최종 임계값

_STORAGE_RE = re.compile(r"(\d+)\s*(GB|TB)", re.IGNORECASE)  # 저장 용량 추출

# 브랜드 키워드 → 정규화 이름 매핑 (부분 일치)
_BRAND_MAP: dict[str, str] = {
    "삼성": "samsung", "samsung": "samsung",
    "마이크론": "micron", "micron": "micron", "crucial": "micron",
    "sk하이닉스": "skhynix", "sk": "skhynix", "hynix": "skhynix",
    "essencore": "essencore", "klevv": "essencore",
    "teamgroup": "teamgroup", "팀그룹": "teamgroup",
    "gskill": "gskill", "g.skill": "gskill",
    "corsair": "corsair", "벤전스": "corsair",
    "kingston": "kingston", "hyperx": "kingston",
    "patriot": "patriot",
    "adata": "adata",
    "geil": "geil",
    "apacer": "apacer",
    "agi": "agi",
    "oloy": "oloy",
    "타무즈": "tammuz", "tammuz": "tammuz",
    "hiksemi": "hiksemi",
    "western": "wd", "wd": "wd",
    "seagate": "seagate",
    "키오시아": "kioxia", "kioxia": "kioxia",
}
_CAPACITY_RE = re.compile(
    r"\b(\d+\s*(?:GB|TB|MHz|CL\d+|DDR[45]?[-]?\d*|NVMe|M\.2|SATA))\b",
    re.IGNORECASE,
)
_NOISE_RE = re.compile(r"[^\w\s]")
_SPACE_RE = re.compile(r"\s+")


def _normalize(name: str) -> str:
    name = name.lower()
    name = _NOISE_RE.sub(" ", name)
    name = _SPACE_RE.sub(" ", name).strip()
    return name


def _extract_brand(name: str) -> str | None:
    lower = name.lower().replace(".", "").replace(" ", "")
    # 길이 내림차순 정렬 → 구체적인 키워드가 먼저 매칭됨 (sk < gskill)
    for keyword in sorted(_BRAND_MAP, key=len, reverse=True):
        if keyword.replace(".", "").replace(" ", "") in lower:
            return _BRAND_MAP[keyword]
    return None


def _extract_tokens(name: str) -> set[str]:
    norm = _normalize(name)
    caps = {m.group(0).lower() for m in _CAPACITY_RE.finditer(name)}
    words = set(norm.split())
    return words | caps


_DDR_RE = re.compile(r"\bDDR(\d)\b", re.IGNORECASE)


def _ddr_gen(name: str) -> int | None:
    m = _DDR_RE.search(name)
    return int(m.group(1)) if m else None


def _storage_gb(name: str) -> int | None:
    """제품명에서 저장 용량(GB 단위로 통일)을 추출. 패키지 합계 용량 우선."""
    # "32GB(16Gx2)" 패턴 — 패키지 합계 용량 사용
    pkg = re.search(r"\((\d+)G(?:B)?x(\d+)\)", name, re.IGNORECASE)
    if pkg:
        return int(pkg.group(1)) * int(pkg.group(2))

    # 단순 GB/TB 패턴
    m = _STORAGE_RE.search(name)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2).upper()
    return val * 1024 if unit == "TB" else val


def match_products(
    danawa_products: list[dict],
    smtcom_products: list[dict],
) -> list[dict]:
    """
    danawa_products 순서를 유지하면서 각 다나와 제품에 최적의 스마트컴 제품 매칭.

    반환 형식:
    [
        {
            "danawa": {...},
            "smtcom": {...} | None,
            "score": float,
        },
        ...
    ]
    """
    smt_names = [p["name"] for p in smtcom_products]
    smt_norms = [_normalize(n) for n in smt_names]
    smt_caps = [_storage_gb(n) for n in smt_names]
    smt_brands = [_extract_brand(n) for n in smt_names]
    smt_ddrs = [_ddr_gen(n) for n in smt_names]

    results = []
    for dw in danawa_products:
        dw_norm = _normalize(dw["name"])
        dw_cap = _storage_gb(dw["name"])
        dw_brand = _extract_brand(dw["name"])
        dw_ddr = _ddr_gen(dw["name"])

        best_score = 0.0
        best_idx = -1

        for i, smt_norm in enumerate(smt_norms):
            # 용량이 명시된 경우 반드시 일치해야 함
            if dw_cap is not None and smt_caps[i] is not None and dw_cap != smt_caps[i]:
                continue
            # 브랜드가 양쪽 모두 식별된 경우 반드시 일치해야 함
            if dw_brand and smt_brands[i] and dw_brand != smt_brands[i]:
                continue
            # DDR 세대가 양쪽 모두 식별된 경우 반드시 일치해야 함
            if dw_ddr and smt_ddrs[i] and dw_ddr != smt_ddrs[i]:
                continue
            score = fuzz.WRatio(dw_norm, smt_norm)
            if score > best_score:
                best_score = score
                best_idx = i

        matched = smtcom_products[best_idx] if best_idx >= 0 and best_score >= MATCH_THRESHOLD else None

        results.append(
            {
                "danawa": dw,
                "smtcom": matched,
                "score": best_score,
            }
        )

    return results


if __name__ == "__main__":
    import asyncio
    from crawler.danawa import crawl as danawa_crawl
    from crawler.smtcom import crawl as smtcom_crawl

    async def _test():
        print("크롤링 중...")
        dw_mem, smt_mem = await asyncio.gather(
            danawa_crawl("memory"),
            smtcom_crawl("memory"),
        )
        print(f"다나와 메모리: {len(dw_mem)}개, 스마트컴 메모리: {len(smt_mem)}개")
        matched = match_products(dw_mem, smt_mem)
        print("\n[메모리 매칭 결과 상위 10개]")
        hit = 0
        for r in matched[:20]:
            dw = r["danawa"]
            smt = r["smtcom"]
            if smt:
                hit += 1
                diff = ""
                if dw["price"] and smt["price"]:
                    gap = smt["price"] - dw["price"]
                    diff = f"  차이: {gap:+,}원"
                print(f"  [{dw['rank']}] {dw['name']}")
                print(f"       ↳ {smt['name']} (score={r['score']:.0f}){diff}")
            else:
                print(f"  [{dw['rank']}] {dw['name']} → 매칭 없음 (score={r['score']:.0f})")
        print(f"\n매칭률: {hit}/{len(matched)} ({hit/len(matched)*100:.1f}%)")

    asyncio.run(_test())
