# -*- coding: utf-8 -*-
"""
chart.html + chart_data.js 를 하나로 합친 '공유용 html' 을 만든다.
- 데이터(js)를 html 안에 인라인하여 파일 하나만 공유해도 열린다.
- 공유용에서는 색상 변경 기능을 제거한다.
- 결과: web/3DMark_{YYMMDD}_share.html   (원본 chart.html / chart_data.js 는 유지)

    python make_share.py
"""
import re
from datetime import datetime
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def main():
    html = (WEB / "chart.html").read_text(encoding="utf-8")
    data = (WEB / "chart_data.js").read_text(encoding="utf-8")

    # 1) 외부 js 참조 → 인라인
    html = html.replace('<script src="chart_data.js"></script>',
                        "<script>\n" + data + "\n</script>")
    # 2) 색상 변경 UI 제거 (마커 사이) — 관련 JS 는 null 가드가 있어 안전
    html = re.sub(r"<!-- COLOR-UI -->.*?<!-- /COLOR-UI -->", "", html, flags=re.S)

    ts = datetime.now().strftime("%y%m%d")
    out = WEB / f"3DMark_{ts}_share.html"
    out.write_text(html, encoding="utf-8")
    print(f"공유용 파일 생성: {out}  ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
