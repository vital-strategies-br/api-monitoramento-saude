import math
import time
from collections import defaultdict

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core import messages
from app.core.config import settings
from app.utils.http import client_ip, error_response, is_public_request


class FixedWindowRateLimiter:
    """Counts requests per client in fixed time windows, in process memory.

    Each worker process keeps its own counters, so the effective ceiling is
    RATE_LIMIT_REQUESTS x number of workers. Counters reset with each window,
    so memory is bounded by the distinct clients seen in one window.
    """

    def __init__(self) -> None:
        self._window = -1
        self._counts: defaultdict[str, int] = defaultdict(int)

    def hit(self, client: str, *, limit: int, window_seconds: int, now: float) -> int | None:
        """Register one request. Return seconds to wait when over the limit, else None."""
        window = int(now // window_seconds)
        if window != self._window:
            self._window = window
            self._counts.clear()

        self._counts[client] += 1
        if self._counts[client] <= limit:
            return None
        return max(1, math.ceil((window + 1) * window_seconds - now))

    def reset(self) -> None:
        self._window = -1
        self._counts.clear()


rate_limiter = FixedWindowRateLimiter()


class RateLimitMiddleware:
    """Returns 429 with Retry-After once a client IP exceeds the configured rate."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._applies(scope):
            await self.app(scope, receive, send)
            return

        retry_after = rate_limiter.hit(
            client_ip(scope),
            limit=settings.RATE_LIMIT_REQUESTS,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
            now=time.monotonic(),
        )
        if retry_after is None:
            await self.app(scope, receive, send)
            return

        response = error_response(
            429,
            messages.RATE_LIMITED.format(segundos=retry_after),
            headers={"Retry-After": str(retry_after)},
        )
        await response(scope, receive, send)

    @staticmethod
    def _applies(scope: Scope) -> bool:
        return (
            scope["type"] == "http"
            and settings.RATE_LIMIT_ENABLED
            and not is_public_request(scope["method"], scope["path"])
            and client_ip(scope) not in settings.rate_limit_exempt_ips_list()
        )
