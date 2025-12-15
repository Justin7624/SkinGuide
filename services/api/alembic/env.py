# services/api/alembic/env.py

from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, pool, text
from alembic import context

from app.db import Base
from app import models  # noqa: F401 (ensure models imported)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    """
    Alembic runs outside the app server, so we keep this simple and read DATABASE_URL
    directly from environment variables.
    """
    return os.getenv("DATABASE_URL", "")


target_metadata = Base.metadata


def _ensure_alembic_version_table(connection) -> None:
    """
    Your revision IDs (e.g. '0005_admin_rbac_sessions_label_queue') are longer than
    Alembic's default alembic_version.version_num VARCHAR(32). This creates the
    version table up-front with a larger column (VARCHAR(128)) so upgrades won't fail.

    Safe to run repeatedly.
    """
    connection.execute(
        text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'alembic_version'
              ) THEN
                CREATE TABLE alembic_version (
                  version_num VARCHAR(128) NOT NULL,
                  CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                );
              END IF;
            END$$;
            """
        )
    )


def run_migrations_offline() -> None:
    url = get_url()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. On Windows cmd.exe use:\n"
            '  set DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/dbname'
        )

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        # Ensure consistent version table naming + PK behavior
        version_table="alembic_version",
        version_table_pk=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_url()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. On Windows cmd.exe use:\n"
            '  set DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/dbname'
        )

    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = url

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Create/ensure alembic_version table with a larger version_num column
        _ensure_alembic_version_table(connection)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # Ensure consistent version table naming + PK behavior
            version_table="alembic_version",
            version_table_pk=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
