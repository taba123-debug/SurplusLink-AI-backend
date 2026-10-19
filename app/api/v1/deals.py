from uuid import UUID

from fastapi import APIRouter

from app.api.v1.marketplace import DB, Org, Manager, Actor, Limit, Offset
from app.schemas.marketplace import DealResponse, PickupDetails
from app.services import deal_service

router = APIRouter(prefix="/deals", tags=["Deals"])


@router.get("", response_model=list[DealResponse])
def list_deals(session: DB, organization: Org, limit: Limit = 50, offset: Offset = 0):
    return deal_service.list_deals(session, organization, limit, offset)


@router.post("/{id}/cancel", response_model=DealResponse)
def cancel(id: UUID, session: DB, organization: Manager, actor: Actor):
    return deal_service.cancel(session, organization, id, actor.user.id)


@router.post("/{id}/complete", response_model=DealResponse, summary="Seller confirms physical collection")
def complete(id: UUID, session: DB, organization: Manager, actor: Actor):
    return deal_service.complete(session, organization, id, actor.user.id)


@router.get("/{id}/pickup-details", response_model=PickupDetails)
def pickup(id: UUID, session: DB, organization: Org):
    return deal_service.pickup_details(session, organization, id)
