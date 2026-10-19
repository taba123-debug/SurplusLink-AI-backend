from fastapi import APIRouter

from app.schemas.health import PingResponse
from app.api.v1.marketplace import router as marketplace_router
from app.api.v1.ai import router as ai_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.offers import router as offers_router
from app.api.v1.deals import router as deals_router
from app.api.v1.payments import router as payments_router
from app.api.v1.dashboard import router as dashboard_router

router = APIRouter()
router.include_router(marketplace_router)
router.include_router(ai_router)
router.include_router(organizations_router)
router.include_router(offers_router)
router.include_router(deals_router)
router.include_router(payments_router)
router.include_router(dashboard_router)


@router.get("/ping", response_model=PingResponse)
def ping() -> PingResponse:
    return PingResponse()
