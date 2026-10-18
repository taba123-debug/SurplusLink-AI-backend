from fastapi import APIRouter

from app.schemas.health import PingResponse

router = APIRouter()


@router.get("/ping", response_model=PingResponse)
def ping() -> PingResponse:
    return PingResponse()
