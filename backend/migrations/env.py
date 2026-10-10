from logging.config import fileConfig

from alembic import context
from app import models  # noqa: F401
from app.config import get_settings
from app.db import Base
from sqlalchemy import create_engine

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=get_settings().sqlalchemy_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(get_settings().sqlalchemy_url).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
