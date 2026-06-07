from fastapi import APIRouter
from app.api.v1.endpoints.deals import router as deals_router
from app.api.v1.endpoints.trends import router as trends_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(deals_router)
api_router.include_router(trends_router)
