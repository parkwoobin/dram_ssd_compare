# -*- coding: utf-8 -*-
"""
gpuId 수집/검증 보조 도구.

gpu_catalog.py 의 gpuId 는 3DMark 전수조사(gpuid API)로 이미 확정돼 있다.
이 스크립트는 그 매핑을 유지보수하기 위한 도구다:

  1) --verify  : 카탈로그의 각 gpuId 가 현재 3DMark 이름과 맞는지 캐시로 대조 (기본)
  2) --find T  : 캐시에서 이름에 T 가 포함된 GPU 의 id 를 검색 (신제품 id 찾기)
  3) --rescan  : gpuid API 로 전체 ID 공간을 재스캔해 캐시(_gpu_id_catalog_full.json) 갱신

차단 예방:
  - gpuid API 는 가벼운 JSON 이지만, --rescan 은 보수적인 동시성/지연을 사용한다.
  - --verify / --find 는 캐시만 읽으므로 네트워크 요청이 전혀 없다(가장 안전).

사용 예:
    python collect_gpu_ids.py                      # = --verify
    python collect_gpu_ids.py --find "9070"
    python collect_gpu_ids.py --rescan --workers 4 --delay 0.15 --max-id 1800
"""
import argparse
import concurrent.futures as cf
import json
import time
import urllib.request
from pathlib import Path

from _common import USER_AGENT
from gpu_catalog import DESKTOP_CATALOG, LAPTOP_CATALOG

HERE = Path(__file__).resolve().parent
CACHE = HERE / "_gpu_id_catalog_full.json"
API = "https://www.3dmark.com/proxycon/ajax/search/gpuid?id={}"
HEADERS = {"User-Agent": USER_AGENT}


def fetch_name(i: int):
    req = urllib.request.Request(API.format(i), headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return i, (data.get("gpuName") or "").strip()
    except Exception:
        return i, ""


def load_cache() -> "dict[int, str]":
    if CACHE.exists():
        raw = json.loads(CACHE.read_text(encoding="utf-8"))
        return {int(k): v for k, v in raw.items()}
    return {}


def rescan(max_id: int, workers: int, delay: float) -> "dict[int, str]":
    print(f"전체 ID 1~{max_id} 재스캔 (workers={workers}, delay={delay}s) ...")
    catalog: "dict[int, str]" = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = []
        for i in range(1, max_id + 1):
            futures.append(ex.submit(fetch_name, i))
            if delay:
                time.sleep(delay)  # 제출 속도 자체를 늦춰 부하/차단 예방
        for fut in cf.as_completed(futures):
            i, name = fut.result()
            if name and name.lower() not in ("", "unknown gpu", "generic vga"):
                catalog[i] = name
    CACHE.write_text(json.dumps(catalog, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"  {len(catalog)}개 GPU 저장 → {CACHE.name}")
    return catalog


def verify(cache: "dict[int, str]") -> None:
    if not cache:
        print("캐시(_gpu_id_catalog_full.json)가 없습니다. 먼저 --rescan 을 실행하세요.")
        return
    issues = 0
    mapped_ids = set()
    for label, cat in (("DESKTOP", DESKTOP_CATALOG), ("LAPTOP", LAPTOP_CATALOG)):
        print(f"\n{'='*60}\n{label}\n{'='*60}")
        for series, models in cat.items():
            for name, gid in models.items():
                if gid is None:
                    print(f"  [미등록] {series:8} / {name}")
                    issues += 1
                    continue
                mapped_ids.add(gid)
                real = cache.get(gid)
                if real is None:
                    print(f"  [캐시없음] {series:8} / {name:16} id={gid}")
                    issues += 1
                else:
                    print(f"  {series:8} / {name:18} id={gid:<5} :: {real}")
    print(f"\n검증 완료. 주의 항목 {issues}건.")

    # 카탈로그에 없는 소비자용 GPU 탐지 (신제품 후보)
    import re
    consumer = re.compile(
        r"GeForce (GTX|RTX|GT) |GeForce GTX|Titan |RTX 40\d0|Radeon RX |Radeon VII|RX Vega",
        re.IGNORECASE,
    )
    missing = [(i, n) for i, n in cache.items()
               if i not in mapped_ids and consumer.search(n)
               and "Max-Q" not in n and "Mobile" not in n]
    if missing:
        print(f"\n[참고] 카탈로그에 없는 소비자용 GPU 후보 {len(missing)}건 "
              f"(원하면 gpu_catalog.py 에 추가):")
        for i, n in sorted(missing, key=lambda x: x[1])[:60]:
            print(f"    id={i:<5} {n}")


def find(cache: "dict[int, str]", term: str) -> None:
    if not cache:
        print("캐시가 없습니다. 먼저 --rescan 을 실행하세요.")
        return
    term_l = term.lower()
    hits = [(i, n) for i, n in cache.items() if term_l in n.lower()]
    if not hits:
        print(f"'{term}' 와 일치하는 GPU 가 없습니다.")
        return
    for i, n in sorted(hits, key=lambda x: x[1]):
        print(f"  id={i:<5} {n}")


def main():
    ap = argparse.ArgumentParser(description="3DMark gpuId 수집/검증 도구")
    ap.add_argument("--verify", action="store_true", help="카탈로그 gpuId 검증(기본)")
    ap.add_argument("--find", metavar="TERM", help="캐시에서 이름으로 id 검색")
    ap.add_argument("--rescan", action="store_true", help="전체 ID 재스캔(캐시 갱신)")
    ap.add_argument("--max-id", type=int, default=1800, help="재스캔 최대 ID")
    ap.add_argument("--workers", type=int, default=4, help="재스캔 동시 요청 수(낮을수록 안전)")
    ap.add_argument("--delay", type=float, default=0.1, help="재스캔 요청 제출 간 지연(초)")
    args = ap.parse_args()

    if args.rescan:
        cache = rescan(args.max_id, args.workers, args.delay)
    else:
        cache = load_cache()

    if args.find:
        find(cache, args.find)
    else:
        # 기본 동작은 검증
        verify(cache)


if __name__ == "__main__":
    main()
