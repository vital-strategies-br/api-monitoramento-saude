from fastapi import APIRouter, Depends

from app.api.v1.endpoints.relation import router as relation_router
from app.api.v1.endpoints.telemetry import router as telemetry_router
from app.api.v1.responses import COMMON_RESPONSES
from app.core.auth_deps import swagger_api_key, swagger_hmac_headers

api_router = APIRouter(dependencies=[Depends(swagger_api_key), Depends(swagger_hmac_headers)])
for router in (relation_router, telemetry_router):
    # Route-level docs override these for the same status code.
    api_router.include_router(router, responses=COMMON_RESPONSES)
