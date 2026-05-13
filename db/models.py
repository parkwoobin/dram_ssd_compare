from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, Index
from sqlalchemy.orm import DeclarativeBase
import enum


class Base(DeclarativeBase):
    pass


class CategoryEnum(str, enum.Enum):
    memory = "memory"
    ssd = "ssd"


class SourceEnum(str, enum.Enum):
    danawa = "danawa"
    smtcom = "smtcom"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(Enum(SourceEnum), nullable=False)
    category = Column(Enum(CategoryEnum), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Integer, nullable=True)          # 원 단위, 품절 시 None
    rank = Column(Integer, nullable=True)           # 다나와 순위
    crawled_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_source_category_crawled", "source", "category", "crawled_at"),
    )


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(Enum(SourceEnum), nullable=False)
    category = Column(Enum(CategoryEnum), nullable=False)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String, default="running")      # running / success / failed
    item_count = Column(Integer, default=0)
    error_message = Column(String, nullable=True)
