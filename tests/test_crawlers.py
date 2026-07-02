"""크롤러 단위 테스트"""
import asyncio
import pytest
from crawler.danawa import crawl as danawa_crawl
from crawler.smtcom import crawl as smtcom_crawl
from crawler.estimates import _matches_names, has_assembly_fee, matching_posts, parse_estimate_detail, parse_posted_at
from crawler.matcher import match_products, _storage_gb, _ddr_gen, _extract_brand


# --- 유틸 함수 테스트 ---

def test_storage_gb_simple():
    assert _storage_gb("삼성전자 DDR5-5600 (16GB)") == 16

def test_storage_gb_package():
    assert _storage_gb("G.SKILL DDR5 (32GB(16Gx2))") == 32

def test_storage_gb_tb():
    assert _storage_gb("SSD M.2 (2TB)") == 2048

def test_storage_gb_none():
    assert _storage_gb("Apacer DDR5-5600 CL46") is None

def test_ddr_gen():
    assert _ddr_gen("삼성전자 DDR5-5600 (16GB)") == 5
    assert _ddr_gen("삼성전자 DDR4-3200 (8GB)") == 4
    assert _ddr_gen("SSD NVMe (1TB)") is None

def test_extract_brand():
    assert _extract_brand("삼성전자 DDR5-5600") == "samsung"
    assert _extract_brand("마이크론 Crucial DDR5") == "micron"
    assert _extract_brand("G.SKILL TRIDENT") == "gskill"


# --- 매처 테스트 ---

def test_match_exact():
    dw = [{"name": "삼성전자 DDR5-5600 (16GB)", "price": 350000, "rank": 1}]
    smt = [{"name": "삼성전자 DDR5-5600 (16GB) PC5-44800", "price": 340000, "smtcom_id": "1"}]
    result = match_products(dw, smt)
    assert len(result) == 1
    assert result[0]["smtcom"] is not None
    assert result[0]["score"] >= 82

def test_match_capacity_mismatch():
    dw = [{"name": "삼성전자 DDR5-5600 (8GB)", "price": 200000, "rank": 1}]
    smt = [{"name": "삼성전자 DDR5-5600 (16GB)", "price": 350000, "smtcom_id": "1"}]
    result = match_products(dw, smt)
    assert result[0]["smtcom"] is None  # 용량 불일치

def test_match_ddr_mismatch():
    dw = [{"name": "삼성전자 DDR5-5600 (8GB)", "price": 200000, "rank": 1}]
    smt = [{"name": "삼성전자 DDR4-3200 (8GB)", "price": 150000, "smtcom_id": "1"}]
    result = match_products(dw, smt)
    assert result[0]["smtcom"] is None  # DDR 세대 불일치


def test_match_rejects_used_memory_to_new_memory():
    dw = [{"name": "삼성전자 DDR4-3200 중고 (16GB) [AS1년보증]", "price": 160600, "rank": 1}]
    smt = [{"name": "삼성전자 DDR4-3200 (16GB)", "price": 265000, "smtcom_id": "1"}]
    result = match_products(dw, smt, category="memory")
    assert result[0]["smtcom"] is None


def test_match_rejects_used_ddr4_2666_memory_to_new_memory():
    smt = [
        {"name": "삼성전자 DDR4-2666 (8GB)", "price": 32000, "smtcom_id": "1"},
        {"name": "삼성전자 DDR4-2666 (16GB)", "price": 61000, "smtcom_id": "2"},
    ]
    for name in ("삼성전자 DDR4-2666 중고 (8GB)", "삼성전자 DDR4-2666 중고 (16GB)"):
        result = match_products([{"name": name, "price": 20000, "rank": 1}], smt, category="memory")
        assert result[0]["smtcom"] is None


def test_match_rejects_laptop_memory_to_desktop_memory():
    dw = [{"name": "삼성전자 노트북 DDR4-3200 (16GB)", "price": 45000, "rank": 1}]
    smt = [{"name": "삼성전자 DDR4-3200 (16GB)", "price": 50000, "smtcom_id": "1"}]
    result = match_products(dw, smt, category="memory")
    assert result[0]["smtcom"] is None


def test_match_allows_laptop_memory_to_laptop_memory():
    dw = [{"name": "삼성전자 노트북 DDR4-3200 (16GB)", "price": 45000, "rank": 1}]
    smt = [{"name": "삼성전자 노트북 DDR4-3200 (16GB)", "price": 50000, "smtcom_id": "1"}]
    result = match_products(dw, smt, category="memory")
    assert result[0]["smtcom"] is not None


def test_match_allows_laptop_memory_with_sodimm_notation():
    dw = [{"name": "삼성전자 노트북 DDR5-5600 (8GB)", "price": 25000, "rank": 1}]
    smt = [{"name": "삼성전자 DDR5-5600 SODIMM (8GB) PC5-44800S", "price": 27000, "smtcom_id": "1"}]
    result = match_products(dw, smt, category="memory")
    assert result[0]["smtcom"] is not None


def test_match_allows_laptop_ddr5_5600_pc5_44800():
    dw = [{"name": "삼성전자 노트북 DDR5-5600 (8GB) PC5-44800", "price": 25000, "rank": 1}]
    smt = [{"name": "삼성전자 노트북 DDR5-5600 (8GB) PC5-44800", "price": 27000, "smtcom_id": "1"}]
    result = match_products(dw, smt, category="memory")
    assert result[0]["smtcom"] is not None


def test_parse_estimate_detail_extracts_target_parts():
    html = """
    <table>
      <tr><th>품목명</th><th>이미지</th><th>상품명</th><th>수량</th><th>가격</th><th>합계</th></tr>
      <tr><td>CPU</td><td></td><td>[AMD] AMD 라이젠7-6세대 9800X3D</td><td>1개</td><td>638,500원</td><td>638,500원</td></tr>
      <tr><td>메모리</td><td></td><td>[PATRIOT] DDR5-6000 16GB</td><td>2개</td><td>305,000원</td><td>610,000원</td></tr>
      <tr><td>쿨러/튜닝</td><td></td><td>[ARCTIC] P12 Pro</td><td>7개</td><td>9,900원</td><td>69,300원</td></tr>
      <tr><td>모니터</td><td></td><td>수집 대상 아님</td><td>1개</td><td>1원</td><td>1원</td></tr>
    </table>
    """
    items = parse_estimate_detail(html, 76972)

    assert [item["part_category"] for item in items] == ["CPU", "메모리", "쿨러"]
    assert items[0]["product_name"] == "AMD 라이젠7-6세대 9800X3D"
    assert items[1]["quantity"] == 2
    assert items[2]["total_price"] == 69300


def test_parse_estimate_detail_ignores_won_in_product_name():
    html = """
    <table>
      <tr><th>품목명</th><th>이미지</th><th>상품명</th><th>수량</th><th>가격</th><th>합계</th></tr>
      <tr>
        <td>메모리</td><td></td>
        <td>[마이크론] 마이크론 Crucial DDR5-5600 CL46 PRO 패키지 대원씨티에스 (128GB(64Gx2))</td>
        <td>1개</td><td></td><td>2,962,900원</td>
      </tr>
    </table>
    """
    items = parse_estimate_detail(html, 77031)

    assert items[0]["product_name"] == "마이크론 Crucial DDR5-5600 CL46 PRO 패키지 대원씨티에스 (128GB(64Gx2))"
    assert items[0]["unit_price"] == 2962900
    assert items[0]["total_price"] == 2962900


def test_parse_posted_at_from_estimate_detail():
    html = "<div>작성일 : 26-06-28 18:28</div>"
    posted_at = parse_posted_at(html)

    assert posted_at is not None
    assert posted_at.strftime("%y-%m-%d %H:%M") == "26-06-28 18:28"


def test_estimate_name_filter_checks_author_only():
    assert _matches_names({"author": "홍길동123", "title": "견적 상담"}, ["홍길동"])
    assert not _matches_names({"author": "김철수", "title": "홍길동님 견적"}, ["홍길동"])


def test_has_assembly_fee_checks_detail_rows():
    html = """
    <table>
      <tr><td>조립비</td><td>컴퓨터 조립 서비스</td><td>1개</td><td>30,000원</td></tr>
    </table>
    """
    assert has_assembly_fee(html)
    assert not has_assembly_fee("<table><tr><td>조립 문의</td><td>가격 없음</td></tr></table>")


def test_matching_posts_keeps_latest_per_author_title():
    posts = [
        {"wr_id": 105, "author": "홍길동", "title": "78"},
        {"wr_id": 104, "author": "홍길동", "title": "다른 견적"},
        {"wr_id": 103, "author": "김철수", "title": "78"},
        {"wr_id": 102, "author": "홍길동", "title": "78"},
        {"wr_id": 101, "author": "김철수", "title": "78"},
    ]

    latest = matching_posts(posts, ["홍길동", "김철수"])

    assert [post["wr_id"] for post in latest] == [105, 104, 103]


def test_match_rejects_used_laptop_memory_to_new_laptop_memory():
    dw = [{"name": "삼성전자 노트북 DDR5-5600 중고 (8GB)", "price": 18000, "rank": 1}]
    smt = [{"name": "삼성전자 DDR5-5600 SODIMM (8GB) PC5-44800S", "price": 27000, "smtcom_id": "1"}]
    result = match_products(dw, smt, category="memory")
    assert result[0]["smtcom"] is None


# --- 크롤러 통합 테스트 (실제 네트워크 필요) ---

@pytest.mark.asyncio
async def test_danawa_memory_crawl():
    products = await danawa_crawl("memory")
    assert len(products) > 10
    for p in products:
        assert "name" in p and p["name"]
        assert "rank" in p

@pytest.mark.asyncio
async def test_danawa_ssd_crawl():
    products = await danawa_crawl("ssd")
    assert len(products) > 10

@pytest.mark.asyncio
async def test_smtcom_memory_crawl():
    products = await smtcom_crawl("memory")
    assert len(products) > 5
    for p in products:
        assert "name" in p and p["name"]

@pytest.mark.asyncio
async def test_smtcom_ssd_crawl():
    products = await smtcom_crawl("ssd")
    assert len(products) > 5
