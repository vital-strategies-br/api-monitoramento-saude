from fastapi import APIRouter
from app.api.v1.endpoints.relacao import router as relacao_router

api_router = APIRouter()
api_router.include_router(relacao_router)
