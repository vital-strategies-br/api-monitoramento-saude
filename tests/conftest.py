import os

import pytest

# Settings require DATABASE_URL at import time; tests never connect to it.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")


@pytest.fixture(autouse=True)
def isolate_from_local_env(monkeypatch):
    """Settings also read .env: keep a developer's local limits out of the tests.

    Tests that exercise the rate limit or the size limits turn them on themselves.
    """
    from app.core.config import Settings, settings
    from app.core.rate_limit import rate_limiter

    defaults = Settings.model_fields
    for name in ("RATE_LIMIT_ENABLED", "RATE_LIMIT_REQUESTS", "RATE_LIMIT_WINDOW_SECONDS",
                 "RATE_LIMIT_EXEMPT_IPS", "MAX_REQUEST_BODY_BYTES", "TELEMETRY_MAX_BATCH_SIZE"):
        monkeypatch.setattr(settings, name, defaults[name].default)
    rate_limiter.reset()
