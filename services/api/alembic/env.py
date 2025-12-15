# services/api/alembic/env.py

from logging.config import fileConfig
import os
from sqlalchemy import engine_from_config, pool
from alembic import context

from app.db import Base
from app import models  # noqa: F401 (ensure models imported)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

def get_url():
    return os.getenv("DATABASE_URL")

target_metadata = Base.metadata

def run_migrations_offline():
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
