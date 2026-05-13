"""크롤러 단위 테스트"""
import asyncio
import pytest
from crawler.danawa import crawl as danawa_crawl
from crawler.smtcom import crawl as smtcom_crawl
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
