from fastapi import APIRouter, Depends
from app.api.v1.endpoints.relacao import router as relacao_router
from app.core.auth_deps import swagger_api_key, swagger_hmac_headers

api_router = APIRouter(dependencies=[Depends(swagger_api_key), Depends(swagger_hmac_headers)])
api_router.include_router(relacao_router)
