# -*- coding: utf-8 -*-
"""
3DMark Graphics score 수집 (데스크탑/노트북 · 여러 벤치마크 통합).

그냥 실행하면 대화형으로 대상/벤치마크를 고른다:
    python scrape.py

옵션으로 바로 지정할 수도 있다:
    python scrape.py --kind desktop --bench timespy
    python scrape.py --kind laptop  --bench firestrike --full
    python scrape.py --kind desktop --bench steelnomad --series "RTX 50"

기본 동작(auto): 최근 24시간 이내 결과가 있으면 신규 GPU만 증분 수집, 아니면 전체.
결과: output/{kind}/{bench}/3dmark_{kind}_{bench}_scores_YYYYMMDD_HHMMSS.xlsx
"""
import argparse
import asyncio

from _common import run_scrape, BENCHMARKS
from gpu_catalog import DESKTOP_CATALOG, LAPTOP_CATALOG


def choose(prompt, options):
    """options: [(key, label), ...] — 번호로 하나 선택."""
    print("\n" + prompt)
    for i, (_k, label) in enumerate(options, 1):
        print(f"  {i}. {label}")
    while True:
        s = input("번호 입력> ").strip()
        if s.isdigit() and 1 <= int(s) <= len(options):
            return options[int(s) - 1][0]
        print("올바른 번호를 입력하세요.")


def main():
    ap = argparse.ArgumentParser(description="3DMark Graphics score 수집")
    ap.add_argument("--kind", choices=["desktop", "laptop"], help="수집 대상")
    ap.add_argument("--bench", choices=list(BENCHMARKS), help="벤치마크")
    ap.add_argument("--series", nargs="*", default=None, help="특정 시리즈만")
    ap.add_argument("--full", action="store_true", help="전체 재수집")
    ap.add_argument("--update", action="store_true", help="신규 GPU만 합치기")
    ap.add_argument("--min-delay", type=float, default=1.0)
    ap.add_argument("--max-delay", type=float, default=2.0)
    args = ap.parse_args()

    kind = args.kind or choose("수집 대상 선택:",
                               [("desktop", "데스크탑"), ("laptop", "노트북")])
    bench = args.bench or choose("벤치마크 선택:",
                                 [(k, BENCHMARKS[k][0]) for k in BENCHMARKS])

    catalog = DESKTOP_CATALOG if kind == "desktop" else LAPTOP_CATALOG
    mode = "full" if args.full else "update" if args.update else "auto"

    asyncio.run(run_scrape(
        catalog, kind, bench,
        series_filter=args.series,
        min_delay=args.min_delay, max_delay=args.max_delay,
        mode=mode,
    ))


if __name__ == "__main__":
    main()
