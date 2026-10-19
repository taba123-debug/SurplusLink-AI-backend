from uuid import UUID

from fastapi import APIRouter

from app.api.v1.marketplace import DB, Org, Manager
from app.schemas.marketplace import OfferResponse
from app.services import offer_service

router = APIRouter(prefix="/offers", tags=["Offers"])


@router.get("/{id}", response_model=OfferResponse)
def detail(id: UUID, session: DB, organization: Org):
    return offer_service.get_offer(session, organization, id)


@router.post("/{id}/withdraw", response_model=OfferResponse)
def withdraw(id: UUID, session: DB, organization: Manager):
    return offer_service.withdraw(session, organization, id)
