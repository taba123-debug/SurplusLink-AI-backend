from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import require_demo, get_identity
from app.schemas.extraction import ParseRequest, LotParseResponse, RequirementParseResponse
from app.services.ai import get_provider, parse

router = APIRouter(prefix="/ai", tags=["AI extraction"], dependencies=[Depends(require_demo), Depends(get_identity)])


@router.post("/parse-lot", response_model=LotParseResponse)
def parse_lot(data: ParseRequest, provider: Annotated[object, Depends(get_provider)]):
    return parse("lot", data.text, provider, data.reference_date, data.timezone)


@router.post("/parse-requirement", response_model=RequirementParseResponse)
def parse_requirement(data: ParseRequest, provider: Annotated[object, Depends(get_provider)]):
    return parse("requirement", data.text, provider, data.reference_date, data.timezone)
