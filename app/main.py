from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.errors import internal_exception_handler
from app.core.logging import configure_logging
from app.core.middleware import RequestLoggingMiddleware
from app.db.session import db_ping

configure_logging()

app = FastAPI(
    title="API Monitoramento Saúde - Vital Strategies Brasil", version="0.1.0"
)

app.include_router(api_router, prefix="/api/v1")
app.add_middleware(RequestLoggingMiddleware)
app.add_exception_handler(Exception, internal_exception_handler)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.get("/health/db", tags=["health"])
async def health_db():
    ok = await db_ping()
    return (
        {"status": "ok", "database": "up"}
        if ok
        else {"status": "degraded", "database": "down"}
    )
