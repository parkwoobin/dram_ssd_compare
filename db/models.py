from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Enum, Index, UniqueConstraint, ForeignKey
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


class DailyPrice(Base):
    __tablename__ = "daily_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    source = Column(Enum(SourceEnum), nullable=False)
    category = Column(Enum(CategoryEnum), nullable=False)
    name = Column(String, nullable=False)
    avg_price = Column(Float, nullable=True)
    min_price = Column(Integer, nullable=True)
    max_price = Column(Integer, nullable=True)
    crawl_count = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("date", "source", "name", name="uq_daily_price"),
        Index("ix_daily_prices_date_cat", "date", "category"),
        Index("ix_daily_prices_lookup", "source", "category", "name", "date"),
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


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    setting_key = Column(String, nullable=False, unique=True)
    setting_value = Column(String, nullable=False, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EstimatePost(Base):
    __tablename__ = "estimate_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    wr_id = Column(Integer, nullable=False, unique=True)
    title = Column(String, nullable=True)
    author = Column(String, nullable=True)
    url = Column(String, nullable=False)
    posted_at = Column(DateTime, nullable=True)
    crawled_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_estimate_posts_wr_id", "wr_id"),
        Index("ix_estimate_posts_author", "author"),
        Index("ix_estimate_posts_crawled", "crawled_at"),
    )


class EstimateItem(Base):
    __tablename__ = "estimate_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("estimate_posts.id"), nullable=False)
    wr_id = Column(Integer, nullable=False)
    part_category = Column(String, nullable=False)
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=True)
    unit_price = Column(Integer, nullable=True)
    total_price = Column(Integer, nullable=True)
    crawled_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("wr_id", "part_category", "product_name", name="uq_estimate_item"),
        Index("ix_estimate_items_category_name", "part_category", "product_name"),
        Index("ix_estimate_items_wr_id", "wr_id"),
    )
