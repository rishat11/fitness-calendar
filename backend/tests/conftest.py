import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fitness:fitness@127.0.0.1:5433/fitness_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-must-be-at-least-32-characters")
os.environ.setdefault("COOKIE_SECURE", "false")

from app.db import get_db
from app.main import app
from app.models.profile import Profile as ProfileModel
from app.models.user import Session as SessionModel
from app.models.user import User as UserModel
from app.services.rate_limit import reset_login_limits
from tests.schema_setup import prepare_test_database, run_alembic

assert UserModel.__tablename__ == "users"
assert SessionModel.__tablename__ == "sessions"
assert ProfileModel.__tablename__ == "profiles"


@pytest.fixture(scope="session")
def migrated_database() -> None:
    prepare_test_database()
    run_alembic("upgrade", "head")
    run_alembic("check")


@pytest.fixture(scope="session")
async def test_engine(migrated_database: None):
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    reset_login_limits()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
    finally:
        app.dependency_overrides.clear()
