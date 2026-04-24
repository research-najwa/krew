from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from pgvector.sqlalchemy import Vector

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=settings.app_env == "development")
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session
