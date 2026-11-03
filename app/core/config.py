from typing import List, Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


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

    @field_validator("API_KEYS")
    @classmethod
    def _strip_api_keys(cls, v: str) -> str:
        return v.strip()

    def api_keys_list(self) -> List[str]:
        return [k.strip() for k in self.API_KEYS.split(",") if k.strip()]

    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]
    
    @property
    def hmac_required(self) -> bool:
        if self.REQUIRE_HMAC is not None:
            return self.REQUIRE_HMAC

        return self.ENV == "prod"


settings = Settings()
