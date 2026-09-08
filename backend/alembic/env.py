"""Alembic environment: runs migrations against the async engine, using app settings."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.core.database import Base

# Import models so they are registered on Base.metadata before autogenerate runs.
from app.addresses import models as addresses_models  # noqa: F401
from app.cart import models as cart_models  # noqa: F401
from app.catalog import models as catalog_models  # noqa: F401
from app.couriers import models as couriers_models  # noqa: F401
from app.notifications import models as notifications_models  # noqa: F401
from app.orders import models as orders_models  # noqa: F401
from app.payments import models as payments_models  # noqa: F401
from app.pickup_point_managers import models as pickup_point_managers_models  # noqa: F401
from app.pickup_points import models as pickup_points_models  # noqa: F401
from app.reports import models as reports_models  # noqa: F401
from app.reviews import models as reviews_models  # noqa: F401
from app.subscriptions import models as subscriptions_models  # noqa: F401
from app.users import models as users_models  # noqa: F401
from app.vendors import models as vendors_models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
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
