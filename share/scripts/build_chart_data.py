# -*- coding: utf-8 -*-
"""
모든 (데스크탑/노트북 × 벤치마크) 최신 결과 xlsx 를 모아 chart.html 이 쓰는
chart_data.js 를 생성한다. 수집을 새로 한 뒤 이 스크립트만 다시 실행하면
그래프가 최신 데이터로 갱신된다.

    python build_chart_data.py
"""
import json
from datetime import datetime
from pathlib import Path

from _common import load_latest_result, BENCHMARKS
from gpu_catalog import DESKTOP_CATALOG, LAPTOP_CATALOG

HERE = Path(__file__).resolve().parent


def _catalog_names(catalog):
    """gpuId -> (시리즈, 표시이름). 카탈로그에서 이름을 바꾸면 다음 빌드에 바로 반영된다.
    (xlsx 에는 수집 당시 이름이 들어있으므로, 현재 카탈로그 이름으로 덮어쓴다.)"""
    m = {}
    for series, models in catalog.items():
        for name, gid in models.items():
            if gid is not None:
                m[gid] = (series, name)
    return m


def main():
    data = {"benchmarks": {k: v[0] for k, v in BENCHMARKS.items()}, "dates": {}}
    for kind in ("desktop", "laptop"):
        names = _catalog_names(DESKTOP_CATALOG if kind == "desktop" else LAPTOP_CATALOG)
        kd, dd = {}, {}
        for bench in BENCHMARKS:
            res, mtime = load_latest_result(kind, bench)
            rows = []
            for gid, (series, model, avg, count, url) in res.items():
                if avg is None:
                    continue
                cur = names.get(gid)        # 현재 카탈로그에 있으면 그 이름/시리즈 사용
                if cur:
                    series, model = cur
                rows.append({
                    "series": series, "model": model,
                    "score": int(avg), "count": int(count) if count is not None else 0,
                    "url": url or "",
                })
            if rows:
                kd[bench] = rows
                # 수집 날짜 = 결과 파일의 최종 저장 시각(가장 최근 수집 기준)
                dd[bench] = datetime.fromtimestamp(mtime).strftime("%Y.%m.%d") if mtime else ""
                print(f"{kind}/{bench}: {len(rows)}개 ({dd[bench]})")
        data[kind] = kd
        data["dates"][kind] = dd

    data["generated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    out = HERE.parent / "web" / "chart_data.js"     # 그래프 폴더(web)에 생성
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("window.CHART_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
                   encoding="utf-8")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
