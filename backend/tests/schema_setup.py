"""Готовит пустую тестовую базу и гоняет Alembic вне цикла pytest."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parents[1]


def prepare_test_database() -> None:
    completed = subprocess.run(
        [sys.executable, str(BACKEND_DIR / "tests" / "schema_setup.py")],
        cwd=BACKEND_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stdout + completed.stderr)


def run_alembic(*args: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stdout + completed.stderr)


async def _reset() -> None:
    url = os.environ["DATABASE_URL"]
    parsed = make_url(url)
    database = parsed.database
    if not database or not database.replace("_", "").isalnum():
        raise RuntimeError("TEST_DATABASE_URL must include a simple database name")
    admin = create_async_engine(
        parsed.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    async with admin.connect() as connection:
        exists = await connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": database},
        )
        if not exists:
            await connection.execute(text(f'CREATE DATABASE "{database}"'))
        await connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": database},
        )
    await admin.dispose()

    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


def main() -> None:
    asyncio.run(_reset(), loop_factory=asyncio.SelectorEventLoop)


if __name__ == "__main__":
    main()
