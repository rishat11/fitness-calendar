import ipaddress

from fastapi import Request
from limits import RateLimitItem, parse
from slowapi import Limiter

from app.config import settings

# Считаются только неудачные входы: декоратор slowapi посчитал бы и успешные.
# Хранилище memory:// живёт в процессе. В compose один процесс uvicorn;
# несколько воркеров сбросят лимит друг у друга, пока нет общего хранилища.
LOGIN_LIMIT: RateLimitItem = parse("10 per 5 minutes")


def client_ip(request: Request) -> str:
    """Адрес клиента. X-Forwarded-For берётся только от доверенного прокси, последний хоп."""
    peer = request.client.host if request.client else "unknown"
    if not _peer_is_trusted(peer):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    parts = [part.strip() for part in forwarded.split(",") if part.strip()]
    return parts[-1] if parts else peer


limiter = Limiter(
    key_func=client_ip,
    strategy="moving-window",
    storage_uri="memory://",
    default_limits=[],
)


def login_is_limited(ip: str, email: str) -> bool:
    return not (_allowed(f"login-ip:{ip}") and _allowed(f"login-email:{email}"))


def record_login_failure(ip: str, email: str) -> None:
    limiter.limiter.hit(LOGIN_LIMIT, f"login-ip:{ip}")
    limiter.limiter.hit(LOGIN_LIMIT, f"login-email:{email}")


def reset_login_limits() -> None:
    limiter.reset()


def _allowed(key: str) -> bool:
    return bool(limiter.limiter.test(LOGIN_LIMIT, key))


def _peer_is_trusted(peer: str) -> bool:
    raw = settings.trusted_proxies.strip()
    if not raw:
        return False
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            if "/" in item:
                if address in ipaddress.ip_network(item, strict=False):
                    return True
            elif address == ipaddress.ip_address(item):
                return True
        except ValueError:
            continue
    return False
