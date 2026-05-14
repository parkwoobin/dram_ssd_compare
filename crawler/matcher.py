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

# SSD 모델 번호 / 시리즈 추출 (다른 시리즈 간 매칭 방지)
_SSD_MODEL_RE = re.compile(
    r"\b("
    r"WD\s*(?:BLACK|BLUE|GREEN|RED|PURPLE|GOLD)"  # WD 컬러 라인 (우선 매칭)
    r"|SN\d{3,}[A-Z0-9]*"                          # WD NVMe 모델: SN850X, SN5000, SN8100
    r"|SA\d{3,}"                                    # WD SATA: SA510
    r"|\d{3,4}\s*(?:PRO|EVO(?:\s*(?:Plus|PLUS))?)" # Samsung 숫자+등급: 990 PRO, 870 EVO
    r"|(?<!\w)(?:980|990|870|880|860|850|970|9100)(?!\s*(?:PRO|EVO|Plus))\b"  # Samsung 단독
    r"|P[3-6]\d\b"                                  # SK Hynix: P31, P41, P51, P61
    r"|PM\d+[A-Z]\d\b"                              # Samsung OEM: PM9A1, PM9C1
    r"|C\d{3,}[A-Z0-9]*\b"                         # KLEVV: C910G, C715, C930
    r"|EXCERIA(?:\s+(?:PRO|PLUS|G\d))?"             # Kioxia: EXCERIA PRO G2, EXCERIA PLUS
    r"|AORUS(?:\s+Gen\d)?"                          # GIGABYTE AORUS 시리즈
    r"|Gen\d\s+\d{4}"                              # GIGABYTE Gen4 7300, Gen3 3500 등
    r"|SPATIUM\s+M\d{3}"                           # MSI SPATIUM M480, M560
    r"|FIRECUDA|BARRACUDA|IRONWOLF"                # Seagate 라인업
    r"|[TX]\d{3,}\b"                               # Crucial: T500, T700
    r"|P\d{3,}\b"                                  # Crucial P310, P510 (P2자리는 SK Hynix)
    r"|NV\d\b"                                     # Kingston: NV3
    r"|LEGEND\s+\d{3,}"                            # ADATA LEGEND 900, 960, 710
    r"|GAMMIX\s+S\d+"                              # ADATA XPG GAMMIX S70
    r"|SX\d{4}"                                    # ADATA XPG SX8200
    r")",
    re.IGNORECASE,
)


_WD_COLOR_KEYS = frozenset({"wdblack", "wdblue", "wdgreen", "wdred", "wdpurple", "wdgold"})


def _ssd_model_keys(name: str) -> set[str]:
    """SSD 모델 식별자 집합 반환. 교집합이 없으면 다른 시리즈 → 매칭 거부."""
    return {re.sub(r"\s+", "", m.group(0).lower()) for m in _SSD_MODEL_RE.finditer(name)}


def _ssd_strong_keys(name: str) -> set[str]:
    """WD 컬러 라인 제외 — 실제 모델 번호만 반환 (SN850X ≠ SN850P 구분 등)."""
    return _ssd_model_keys(name) - _WD_COLOR_KEYS


def _ssd_model(name: str) -> str | None:
    """단일 모델 번호 반환 (하위 호환)."""
    keys = _ssd_model_keys(name)
    return next(iter(keys)) if keys else None


def _model_keys_compatible(a: set[str], b: set[str]) -> bool:
    """교집합이 있거나, 한쪽 키가 다른쪽 키의 prefix이면 호환 (SN5000S ↔ SN5000)."""
    if a & b:
        return True
    return any(ka.startswith(ks) or ks.startswith(ka) for ka in a for ks in b)

# 브랜드 키워드 → 정규화 이름 매핑 (부분 일치)
_BRAND_MAP: dict[str, str] = {
    "삼성": "samsung", "samsung": "samsung",
    "마이크론": "micron", "micron": "micron", "crucial": "micron",
    "sk하이닉스": "skhynix", "sk": "skhynix", "hynix": "skhynix",
    "essencore": "essencore", "klevv": "essencore",
    "teamgroup": "teamgroup", "팀그룹": "teamgroup",
    "gskill": "gskill", "g.skill": "gskill",
    "corsair": "corsair", "벤전스": "corsair",
    "kingston": "kingston", "킹스톤": "kingston", "hyperx": "kingston",
    "patriot": "patriot",
    "adata": "adata",
    "geil": "geil",
    "apacer": "apacer",
    "agi": "agi",
    "oloy": "oloy",
    "타무즈": "tammuz", "tammuz": "tammuz",
    "hiksemi": "hiksemi", "hikvision": "hiksemi",
    "western": "wd", "wd": "wd",
    "seagate": "seagate",
    "키오시아": "kioxia", "kioxia": "kioxia",
    "biwin": "biwin",
    "컴이지": "comeasy", "comeasy": "comeasy",
    "화이트스톤": "whitestone",
    "실리콘파워": "siliconpower", "silicon power": "siliconpower",
    "넥스트": "next",
    "타무즈": "tammuz",
    "마이크로닉스": "micronics", "micronics": "micronics",
    "gigabyte": "gigabyte", "기가바이트": "gigabyte",
    "화웨이": "huawei", "huawei": "huawei",
    "파이슨": "phison", "phison": "phison",
}
_CAPACITY_RE = re.compile(
    r"\b(\d+\s*(?:GB|TB|MHz|CL\d+|DDR[45]?[-]?\d*|NVMe|M\.2|SATA))\b",
    re.IGNORECASE,
)
_NOISE_RE = re.compile(r"[^\w\s]")
_SPACE_RE = re.compile(r"\s+")
_USED_RE = re.compile(r"(중고|리퍼|refurbished|\bused\b)", re.IGNORECASE)
_LAPTOP_MEMORY_RE = re.compile(
    r"(노트북|랩탑|laptop|SODIMM|SO-DIMM|SO DIMM|소디imm|소디|온보드|"
    r"PC\d-\d{5}S\b|\b\d{5}S\b)",
    re.IGNORECASE,
)


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


def _is_used(name: str) -> bool:
    return bool(_USED_RE.search(name))


def _is_laptop_memory(name: str) -> bool:
    return bool(_LAPTOP_MEMORY_RE.search(name))


def _memory_variant_compatible(danawa_name: str, smtcom_name: str) -> bool:
    """중고/노트북 메모리를 일반 신품 데스크탑 메모리와 섞어 매칭하지 않는다."""
    if _is_used(danawa_name) != _is_used(smtcom_name):
        return False
    if _is_laptop_memory(danawa_name) != _is_laptop_memory(smtcom_name):
        return False
    return True


_SSD_CAPACITY_CLASSES = (
    (0,    150,   128),
    (150,  300,   256),
    (300,  600,   512),
    (600,  1200,  1024),
    (1200, 2500,  2048),
    (2500, 5000,  4096),
    (5000, 10000, 8192),
)


def _ssd_capacity_class(gb: int) -> int:
    """500/512 등 미묘하게 다른 용량 표기를 업계 표준 클래스로 정규화."""
    for lo, hi, cls in _SSD_CAPACITY_CLASSES:
        if lo < gb <= hi:
            return cls
    return gb


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
    category: str = "memory",
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
    smt_used = [_is_used(n) for n in smt_names]
    smt_laptop_memory = [_is_laptop_memory(n) for n in smt_names]
    is_ssd = category == "ssd"
    smt_model_keys_list = [_ssd_model_keys(n) for n in smt_names] if is_ssd else [set()] * len(smt_names)
    smt_strong_keys_list = [_ssd_strong_keys(n) for n in smt_names] if is_ssd else [set()] * len(smt_names)

    results = []
    for dw in danawa_products:
        dw_norm = _normalize(dw["name"])
        dw_cap = _storage_gb(dw["name"])
        dw_brand = _extract_brand(dw["name"])
        dw_ddr = _ddr_gen(dw["name"])
        dw_used = _is_used(dw["name"])
        dw_laptop_memory = _is_laptop_memory(dw["name"])
        dw_model_keys = _ssd_model_keys(dw["name"]) if is_ssd else set()
        dw_strong_keys = _ssd_strong_keys(dw["name"]) if is_ssd else set()

        best_score = 0.0
        best_idx = -1

        dw_cap_class = _ssd_capacity_class(dw_cap) if is_ssd and dw_cap else dw_cap
        smt_cap_classes = [(_ssd_capacity_class(c) if is_ssd and c else c) for c in smt_caps]

        for i, smt_norm in enumerate(smt_norms):
            if category == "memory":
                if dw_used != smt_used[i]:
                    continue
                if dw_laptop_memory != smt_laptop_memory[i]:
                    continue
            # 용량이 명시된 경우 반드시 일치해야 함 (SSD는 클래스 단위 비교: 500GB≈512GB)
            cap_dw = dw_cap_class if is_ssd else dw_cap
            cap_smt = smt_cap_classes[i] if is_ssd else smt_caps[i]
            if cap_dw is not None and cap_smt is not None and cap_dw != cap_smt:
                continue
            # 브랜드가 양쪽 모두 식별된 경우 반드시 일치해야 함
            if dw_brand and smt_brands[i] and dw_brand != smt_brands[i]:
                continue
            # DDR 세대가 양쪽 모두 식별된 경우 반드시 일치해야 함
            if dw_ddr and smt_ddrs[i] and dw_ddr != smt_ddrs[i]:
                continue
            # SSD: 모델 키 집합이 호환되지 않으면 다른 시리즈 → 매칭 거부
            if is_ssd and dw_model_keys and smt_model_keys_list[i] and not _model_keys_compatible(dw_model_keys, smt_model_keys_list[i]):
                continue
            # SSD: 실제 모델 번호(WD 컬러라인 제외)가 양쪽 모두 있는데 호환 안되면 → 매칭 거부 (SN850P ≠ SN850X)
            if is_ssd and dw_strong_keys and smt_strong_keys_list[i] and not _model_keys_compatible(dw_strong_keys, smt_strong_keys_list[i]):
                continue
            score = fuzz.WRatio(dw_norm, smt_norm)
            effective_threshold = MATCH_THRESHOLD
            # 다나와 브랜드가 식별되는데 스마트컴 브랜드가 불명이면 높은 임계값 요구
            if dw_brand and not smt_brands[i]:
                effective_threshold = max(effective_threshold, 93)
            # 스마트컴 제품은 특정 모델인데 다나와 제품이 generic이면 높은 임계값 요구
            if is_ssd and smt_model_keys_list[i] and not dw_model_keys:
                effective_threshold = max(effective_threshold, 95)
            if score < effective_threshold:
                continue
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
