from fastapi import APIRouter, Depends
from app.api.v1.endpoints.relation import router as relation_router
from app.core.auth_deps import swagger_api_key, swagger_hmac_headers

api_router = APIRouter(dependencies=[Depends(swagger_api_key), Depends(swagger_hmac_headers)])
api_router.include_router(relation_router)
