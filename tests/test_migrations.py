import pytest
from alembic import command
from alembic.config import Config
from app.config import ROOT, get_settings
from app.db import Base
from sqlalchemy import create_engine, inspect


@pytest.mark.integration
async def test_alembic_creates_the_business_schema_from_empty_database(pg):
    # pg belongs to pytest's random disposable database, never the application database.
    engine = create_engine(get_settings().sqlalchemy_url)
    try:
        Base.metadata.drop_all(engine)
        config = Config(str(ROOT / "alembic.ini"))
        command.upgrade(config, "head")
        inspector = inspect(engine)
        for name, table in Base.metadata.tables.items():
            assert inspector.has_table(name)
            assert {column["name"] for column in inspector.get_columns(name)} == set(table.columns.keys())
        command.downgrade(config, "base")
        assert not inspect(engine).has_table("research_runs")
        command.upgrade(config, "head")
        assert inspect(engine).has_table("approvals")
    finally:
        engine.dispose()
