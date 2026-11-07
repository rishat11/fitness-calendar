import pytest
from app.config import Settings, settings
from app.db import get_db
from app.main import app
from app.services.auth import hash_token, new_session_token, open_token
from app.services.rate_limit import (
    client_ip,
    login_is_limited,
    record_login_failure,
    reset_login_limits,
)
from fastapi import Request
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from tests.schema_setup import run_alembic


def test_alembic_check_reports_no_drift(migrated_database: None) -> None:
    run_alembic("check")


def test_session_cookie_is_signed_with_secret() -> None:
    cookie, digest = new_session_token()
    raw = open_token(cookie)
    assert raw is not None
    assert hash_token(raw) == digest
    assert open_token(raw) is None
    assert open_token(cookie + "ab") is None


def test_placeholder_secret_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+asyncpg://fitness:fitness@localhost/fitness",
            secret_key="change-me-to-a-long-random-string",
        )


def test_cookie_secure_defaults_to_true() -> None:
    assert Settings.model_fields["cookie_secure"].default is True


def test_forwarded_for_is_used_only_for_a_trusted_proxy() -> None:
    previous = settings.trusted_proxies
    settings.trusted_proxies = "10.0.0.5, 10.1.0.0/16"
    try:
        from_proxy = _request("10.0.0.5", "1.2.3.4, 203.0.113.8")
        assert client_ip(from_proxy) == "203.0.113.8"
        from_network = _request("10.1.4.4", "203.0.113.9")
        assert client_ip(from_network) == "203.0.113.9"
        spoofed = _request("192.168.1.20", "203.0.113.8")
        assert client_ip(spoofed) == "192.168.1.20"
    finally:
        settings.trusted_proxies = previous


def test_login_limit_is_separate_for_ip_and_email() -> None:
    reset_login_limits()
    try:
        for index in range(10):
            email = f"user{index}@example.com"
            assert login_is_limited("203.0.113.5", email) is False
            record_login_failure("203.0.113.5", email)
        assert login_is_limited("203.0.113.5", "fresh@example.com") is True

        reset_login_limits()
        for index in range(10):
            record_login_failure(f"198.51.100.{index + 1}", "target@example.com")
        assert login_is_limited("203.0.113.50", "target@example.com") is True
        assert login_is_limited("203.0.113.50", "other@example.com") is False
    finally:
        reset_login_limits()


async def test_health_returns_503_when_database_fails(client) -> None:
    class Broken:
        async def execute(self, *_args: object, **_kwargs: object) -> None:
            raise OperationalError("SELECT 1", {}, OSError("db down"))

    async def override():
        yield Broken()

    app.dependency_overrides[get_db] = override
    response = await client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def _request(host: str, forwarded: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers,
        "client": (host, 1234),
        "server": ("test", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    return Request(scope)
