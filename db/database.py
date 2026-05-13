import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv
from db.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/prices.db")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
