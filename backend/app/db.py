from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


def now() -> datetime:
    return datetime.now(UTC)


def uid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    get_settings().sqlalchemy_url,
    pool_pre_ping=True,
    pool_size=8,
    max_overflow=8,
    connect_args={"connect_timeout": 8},
)
Session = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope():
    async with Session() as session:
        async with session.begin():
            yield session


async def get_session():
    async with Session() as session:
        yield session
