from typing import List, Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

from app.utils.text import split_csv


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Environment
    ENV: Literal["dev", "prod"] = "dev"

    # DB (pre-existing)
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 5
    DATABASE_POOL_TIMEOUT: int = 60  # seconds

    # Auth
    # Comma-separated list of keys: "key1,key2,key3"
    API_KEYS: str = ""
    API_SECRET: str = ""

    # HMAC / Timestamp
    REQUIRE_HMAC: Optional[bool] = None
    TIMESTAMP_TOLERANCE_SECONDS: int = 300

    # CORS / Origin allowlist
    # Comma-separated: "http://localhost:3000,chrome-extension://abcdef..."
    ALLOWED_ORIGINS: str = ""
    ENFORCE_ORIGIN_CHECK: bool = True

    # Telemetry: maximum events per POST /api/v1/telemetria/eventos batch
    TELEMETRY_MAX_BATCH_SIZE: int = Field(default=200, gt=0)

    # Maximum request body, in bytes, for every authenticated route.
    # Checked before authentication reads the body.
    MAX_REQUEST_BODY_BYTES: int = Field(default=1_048_576, gt=0)

    # Rate limit per client IP on authenticated routes (fixed window, per worker process).
    # Client IP comes from X-Forwarded-For only for proxies listed in FORWARDED_ALLOW_IPS.
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_REQUESTS: int = Field(default=120, gt=0)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, gt=0)
    # Comma-separated client IPs never rate limited (e.g. the Pitang backend outbound IP)
    RATE_LIMIT_EXEMPT_IPS: str = ""

    @field_validator("API_KEYS")
    @classmethod
    def _strip_api_keys(cls, v: str) -> str:
        return v.strip()

    def api_keys_list(self) -> List[str]:
        return split_csv(self.API_KEYS)

    def allowed_origins_list(self) -> List[str]:
        return split_csv(self.ALLOWED_ORIGINS)

    def rate_limit_exempt_ips_list(self) -> List[str]:
        return split_csv(self.RATE_LIMIT_EXEMPT_IPS)

    @property
    def hmac_required(self) -> bool:
        if self.REQUIRE_HMAC is not None:
            return self.REQUIRE_HMAC

        return self.ENV == "prod"


settings = Settings()
