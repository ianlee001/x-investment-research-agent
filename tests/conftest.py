import asyncio
import os
import secrets
import sys

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

_test_database = None
_admin_dsn = None


def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", help="Use a new isolated PostgreSQL test database")


def pytest_configure(config):
    global _test_database, _admin_dsn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if config.getoption("--integration"):
        from app.config import get_settings

        dsn = get_settings().db_url
        _admin_dsn = make_conninfo(dsn, dbname="postgres")
        _test_database = "xresearch_test_" + secrets.token_hex(6)
        with psycopg.connect(_admin_dsn, autocommit=True, connect_timeout=8) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {} ").format(sql.Identifier(_test_database)))
        # URL form is retained for SQLAlchemy; do not print it (it contains credentials).
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(dsn)
        os.environ["DATABASE_URL"] = urlunsplit(parts._replace(path="/" + _test_database))
        get_settings.cache_clear()


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip = pytest.mark.skip(reason="Use --integration to run against an isolated PostgreSQL database")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)


@pytest.fixture
async def pg():
    from app import models  # noqa: F401
    from app.config import get_settings
    from app.db import Base, engine
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.store.postgres.aio import AsyncPostgresStore
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncConnectionPool(
        get_settings().db_url,
        min_size=1,
        max_size=6,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    ) as pool:
        saver, store = AsyncPostgresSaver(pool), AsyncPostgresStore(pool)
        await saver.setup()
        await store.setup()
        yield saver, store
    await engine.dispose()


def pytest_sessionfinish(session, exitstatus):
    if _test_database:
        with psycopg.connect(_admin_dsn, autocommit=True, connect_timeout=8) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(_test_database)))
