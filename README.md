# DRAM & SSD 가격 비교 서비스

다나와와 스마트컴의 메모리(RAM), SSD 가격을 수집/저장하고 비교하는 FastAPI 기반 웹 서비스입니다.

## 현재 상태 요약

- 비교 API는 실시간 크롤링이 아니라 DB 최신 스냅샷 기준으로 동작
- 가격 추세는 일별 집계 데이터(`daily_prices`) + 당일 실시간 평균 fallback으로 표시
- 스케줄러는 매 정각 실행되며, 기본 수집 시간대는 09:00~18:00(KST)
- 프론트는 필터/정렬/차트 UI가 개선된 상태
  - 필터 버튼 래핑/정렬 보정
  - 차트 범례 마커 정사각형 표시
  - 차트 텍스트 크기 확대
  - 행 hover 미니 차트 팝업
  - 하단 GitHub 링크 추가

## 주요 기능

- 다나와/스마트컴 메모리·SSD 가격 수집
- 다나와 제품 기준 스마트컴 매칭 비교
- 정렬 지원
  - `popular`: 다나와 rank 기준 정렬
  - `newest`: 현재 별도 신규 기준 미적용(동일 데이터셋)
  - `price_asc`, `price_desc`: 스마트컴 가격 기준 정렬
- 메모리 필터
  - DDR4/DDR5, ECC 제외, 용량(4/8/16/24/32/48/64/96/128/256GB)
- SSD 필터
  - 용량(256/512/1024/2048/4096GB)
- 가격 추세
  - 제품별 일별 평균 가격 그래프
  - 테스트용 디버그 차트 API 제공

## 기술 스택

- Backend: FastAPI, Pydantic, SQLAlchemy Async, aiosqlite
- Scheduler: APScheduler (AsyncIOScheduler)
- Crawling: Playwright, BeautifulSoup
- Frontend: Vanilla HTML/CSS/JS, Chart.js
- DB: SQLite

## 프로젝트 구조

```text
dram_ssd_compare/
├── api/
│   ├── main.py
│   └── routes/
│       ├── compare.py
│       └── trend.py
├── crawler/
│   ├── danawa.py
│   ├── matcher.py
│   └── smtcom.py
├── db/
│   ├── crud.py
│   ├── database.py
│   └── models.py
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── scheduler/jobs.py
├── tests/test_crawlers.py
├── requirements.txt
└── README.md
```

## 데이터 모델

- `products`
  - 소스별/카테고리별 시점 스냅샷 (name, price, rank, crawled_at)
- `daily_prices`
  - 날짜별 평균/최저/최고/집계횟수
- `crawl_logs`
  - 크롤링 실행 로그(시작/종료/성공여부/에러)

## 스케줄링

- 크롤링 작업: 매 정각 트리거
  - 내부 시간 가드로 기본 09:00~18:00만 실제 수집
  - 환경변수로 범위 변경 가능: `CRAWL_START_HOUR`, `CRAWL_END_HOUR`
- 일별 집계 작업: 매일 18:05(KST)

## API 엔드포인트

- `GET /api/compare/{category}`
  - `category`: `memory` | `ssd`
  - query
    - `sort`: `popular|newest|price_asc|price_desc`
    - `ddr`: `4|5` (memory)
    - `ecc_exclude`: `true|false` (memory)
    - `capacity_gb`: 용량 필터

- `GET /api/trend/products`
  - query: `category=memory|ssd`

- `GET /api/trend/history`
  - query: `category`, `danawa_name`, `smtcom_name(optional)`, `days(7~365)`

- `GET /api/trend/daily-history`
  - `trend/history`와 동일, 일별 데이터 중심(오늘은 실시간 평균 fallback 포함)

- `GET /api/trend/test-debug`
  - 프론트 차트 확인용 테스트 데이터

- `GET /health`
  - 헬스체크

## 실행 방법 (Windows)

```powershell
# 1) 가상환경
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2) 의존성 설치
pip install -r requirements.txt
playwright install chromium

# 3) DB 초기화
python -m db.database

# 4) 서버 실행
.\venv\Scripts\python.exe -m uvicorn api.main:app --host localhost --port 8000
```

접속: http://localhost:8000

## 운영 참고

- 앱 시작 시 DB가 비어 있으면 초기 강제 크롤링을 1회 수행합니다.
- 현재 정렬의 `newest`는 데이터 소스 특성상 별도 신규 기준이 아직 적용되지 않았습니다.

## 환경변수

현재 코드에서 실제로 사용하는 환경변수는 아래 2개입니다.

| 변수명 | 기본값 | 설명 |
|---|---:|---|
| `CRAWL_START_HOUR` | `9` | 크롤링 허용 시작 시각(KST, 포함) |
| `CRAWL_END_HOUR` | `18` | 크롤링 허용 종료 시각(KST, 미포함) |

예시:

```powershell
$env:CRAWL_START_HOUR = "8"
$env:CRAWL_END_HOUR = "20"
.\venv\Scripts\python.exe -m uvicorn api.main:app --host localhost --port 8000
```

## 프로세스 실행 예시

### 1) 콘솔 직접 실행

```powershell
.\venv\Scripts\Activate.ps1
.\venv\Scripts\python.exe -m uvicorn api.main:app --host localhost --port 8000
```

### 2) 백그라운드 실행 (PowerShell)

```powershell
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "-m uvicorn api.main:app --host localhost --port 8000" -WorkingDirectory "D:\dram_ssd_compare"
```

### 3) 포트 점유 프로세스 종료 후 재기동

```powershell
$procs = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
if ($procs) { Stop-Process -Id $procs -Force -ErrorAction SilentlyContinue }
.\venv\Scripts\python.exe -m uvicorn api.main:app --host localhost --port 8000
```

## 장애 대응 체크리스트

- 서버 기동 확인
  - `GET /health` 응답이 `{"status":"ok"}` 인지 확인
- 데이터 미표시 확인
  - `Product` 테이블 최신 `crawled_at` 시각 확인
  - 필요 시 수동 크롤링(`crawl_all(force=True)`) 실행
- 정렬/필터 결과 이상
  - `/api/compare/{category}` 호출 파라미터(`sort`, `ddr`, `capacity_gb`) 확인
- 추세 차트 비어 있음
  - `daily_prices` 집계 여부 확인
  - 집계 전이라면 `/api/trend/test-debug`로 프론트 렌더링 우선 점검
- 포트 충돌/재기동 실패
  - 8000 포트 점유 PID 종료 후 재기동
  - 가상환경 활성화 및 의존성 설치 상태 재확인

## 링크

- GitHub: https://github.com/parkwoobin/dram_ssd_compare

## 라이선스

Private
