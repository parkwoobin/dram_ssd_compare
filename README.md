# DRAM & SSD 가격 비교 서비스

다나와와 스마트컴의 메모리(RAM) 및 SSD 가격을 자동으로 수집하여 비교하는 웹 서비스입니다.

## 주요 기능

- 다나와 / 스마트컴 메모리·SSD 가격 자동 수집 (매일 09:00~18:00, 1시간 간격)
- 다나와 제품명 기준으로 스마트컴 제품 매칭 및 비교
- 인기상품순 / 신상품순 / 낮은가격순 / 높은가격순 정렬
- 마지막 크롤링 시각 표시

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 크롤러 | Python + Playwright |
| 스케줄러 | APScheduler |
| 백엔드 API | FastAPI |
| 데이터베이스 | SQLite (개발) → PostgreSQL (운영) |
| 프론트엔드 | Vanilla HTML/CSS/JS (또는 React) |
| 배포 | 추후 결정 |

---

## 프로젝트 구조

```
dram_ssd_compare/
├── README.md
├── requirements.txt
├── .env.example
├── crawler/
│   ├── __init__.py
│   ├── danawa.py          # 다나와 크롤러
│   └── smtcom.py          # 스마트컴 크롤러
├── db/
│   ├── __init__.py
│   ├── database.py        # DB 연결 및 초기화
│   ├── models.py          # 테이블 스키마
│   └── crud.py            # CRUD 함수
├── scheduler/
│   ├── __init__.py
│   └── jobs.py            # APScheduler 크롤링 작업
├── api/
│   ├── __init__.py
│   ├── main.py            # FastAPI 앱 진입점
│   └── routes/
│       ├── memory.py      # 메모리 비교 API
│       └── ssd.py         # SSD 비교 API
├── frontend/
│   ├── index.html         # 메인 페이지
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
└── tests/
    ├── test_danawa.py
    └── test_smtcom.py
```

---

## 구현 단계

### Phase 1 — 환경 세팅
- [x] README.md 작성
- [ ] `requirements.txt` 작성
- [ ] `.env.example` 작성
- [ ] Python 가상환경 구성

### Phase 2 — 데이터베이스
- [ ] SQLite 스키마 설계 (products, prices, crawl_logs)
- [ ] SQLAlchemy 모델 구현
- [ ] CRUD 함수 구현

### Phase 3 — 크롤러
- [ ] Playwright 설치 및 브라우저 설정
- [ ] 다나와 크롤러 구현 (메모리 / SSD)
- [ ] 스마트컴 크롤러 구현 (메모리 / SSD)
- [ ] 크롤러 단독 실행 테스트

### Phase 4 — 데이터 매칭
- [ ] 다나와 제품명 기준으로 스마트컴 제품 매칭 알고리즘
- [ ] 정규화 로직 (용량·규격 파싱)

### Phase 5 — 백엔드 API
- [ ] FastAPI 앱 기본 세팅
- [ ] 메모리 비교 엔드포인트
- [ ] SSD 비교 엔드포인트
- [ ] 정렬 파라미터 처리 (popular / newest / price_asc / price_desc)

### Phase 6 — 스케줄러
- [ ] APScheduler 설정 (09:00~18:00, 1시간 간격)
- [ ] 크롤링 작업 등록 및 로그 기록

### Phase 7 — 프론트엔드
- [ ] 메인 페이지 레이아웃 (메모리 탭 / SSD 탭)
- [ ] 정렬 버튼 UI
- [ ] 가격 비교 테이블 컴포넌트
- [ ] 마지막 업데이트 시각 표시

### Phase 8 — 통합 테스트
- [ ] 크롤러 단위 테스트
- [ ] API 통합 테스트
- [ ] 스케줄러 동작 확인

### Phase 9 — 배포 준비 (추후)
- [ ] 배포 환경 결정 (VPS / Cloud)
- [ ] PostgreSQL 마이그레이션
- [ ] Docker 컨테이너화
- [ ] HTTPS 설정

---

## 크롤링 대상

### 다나와
- URL: https://shop.danawa.com/virtualestimate/?controller=estimateMain&methods=index&marketPlaceSeq=16
- 수집 항목: 메모리, SSD 섹션의 제품명 / 가격 / 순위

### 스마트컴
- URL: https://www.smtcom.co.kr/shop/estimatepc.html
- 수집 항목: 메모리, SSD 섹션의 제품명 / 가격

---

## 실행 방법 (개발)

```bash
# 1. 가상환경 생성 및 활성화
python -m venv venv
venv\Scripts\activate  # Windows

# 2. 의존성 설치
pip install -r requirements.txt
playwright install chromium

# 3. DB 초기화
python -m db.database

# 4. 크롤러 수동 실행 (테스트)
python -m crawler.danawa
python -m crawler.smtcom

# 5. 서버 실행 (스케줄러 포함)
uvicorn api.main:app --reload --port 8000
```

---

## 라이선스

Private
