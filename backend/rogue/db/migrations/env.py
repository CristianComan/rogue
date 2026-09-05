import asyncio
from logging.config import fileConfig
from typing import Literal

from alembic import context
from geoalchemy2.alembic_helpers import render_item
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.sql.schema import SchemaItem

from rogue.db import models  # noqa: F401  (registers ORM models on Base.metadata)
from rogue.db.base import Base
from rogue.settings import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The URL always comes from ROGUE_DATABASE_URL (via pydantic-settings), not
# the placeholder in alembic.ini, so the same settings module used by the
# API is the single source of truth for where migrations run.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

# The postgis/postgis image ships the tiger geocoder and topology
# extensions pre-installed, which reflect as dozens of unrelated tables
# (county, edges, spatial_ref_sys, ...). Autogenerate must not propose
# dropping any of those — only compare against tables this project owns.
_OWNED_TABLES = frozenset(target_metadata.tables)


_ObjectType = Literal[
    "schema",
    "table",
    "column",
    "index",
    "unique_constraint",
    "foreign_key_constraint",
    "check_constraint",
]


def _include_object(
    object: SchemaItem,
    name: str | None,
    type_: _ObjectType,
    reflected: bool,
    compare_to: SchemaItem | None,
) -> bool:
    if type_ == "table":
        return (not reflected) or name in _OWNED_TABLES
    table = getattr(object, "table", None)
    return table is None or table.name in _OWNED_TABLES


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
