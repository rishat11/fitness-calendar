import asyncio
from logging.config import fileConfig

from alembic import context
from app.config import settings
from app.models import (
    Block,
    BlockPlacement,
    BlockScheduleItem,
    BlockWeek,
    Exercise,
    NutritionIntake,
    PerformedItem,
    PerformedWorkout,
    PlanChangeLog,
    PlannedWorkout,
    Profile,
    ProgressionDecision,
    Session,
    SetLog,
    User,
)
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = User.metadata
assert Session.metadata is target_metadata
assert Profile.metadata is target_metadata
assert Exercise.metadata is target_metadata
assert PlannedWorkout.metadata is target_metadata
assert PlanChangeLog.metadata is target_metadata
assert NutritionIntake.metadata is target_metadata
assert PerformedWorkout.metadata is target_metadata
assert PerformedItem.metadata is target_metadata
assert SetLog.metadata is target_metadata
assert ProgressionDecision.metadata is target_metadata
assert Block.metadata is target_metadata
assert BlockWeek.metadata is target_metadata
assert BlockScheduleItem.metadata is target_metadata
assert BlockPlacement.metadata is target_metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
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


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
