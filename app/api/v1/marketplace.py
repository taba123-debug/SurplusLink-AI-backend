from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_demo_org, get_manager_org, get_identity, require_demo
from app.core.security import DemoIdentity
from app.models import Organization, SurplusLot, BuyerRequirement
from app.schemas.marketplace import (LotCreate, LotPublic, RequirementCreate, RequirementPublic,
    OfferCreate, OfferResponse, Respond, RespondResponse, DealResponse, CheckoutResponse, LotMatch, BuyerMatch, DemoOrganization)
from app.services import marketplace as service
from app.services import catalog
from app.schemas.marketplace import LotPrivate, LotPatch, RequirementPatch, DemoIdentityOption

router = APIRouter(dependencies=[Depends(require_demo)])
DB = Annotated[Session, Depends(get_db)]
Org = Annotated[Organization, Depends(get_demo_org)]
Manager = Annotated[Organization, Depends(get_manager_org)]
Actor = Annotated[DemoIdentity, Depends(get_identity)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/demo/organizations", response_model=list[DemoOrganization], tags=["Demo context"])
def organizations(session: DB):
    return catalog.public_organizations(session)


@router.get("/demo/identities", response_model=list[DemoIdentityOption], tags=["Demo context"])
def identities(session: DB):
    return catalog.demo_identities(session)


@router.post("/lots", response_model=LotPublic, status_code=201, tags=["Inventory"])
def create_lot(data: LotCreate, session: DB, organization: Manager):
    return service.create_lot(session, organization, data)


@router.get("/lots", response_model=list[LotPublic], tags=["Inventory"])
def list_lots(session: DB, limit: Limit = 50, offset: Offset = 0):
    return catalog.public_lots(session, limit, offset)


@router.get("/lots/mine", response_model=list[LotPrivate], tags=["Inventory"])
def own_lots(session: DB, organization: Org, limit: Limit = 50, offset: Offset = 0):
    return catalog.own_lots(session, organization, limit, offset)


@router.get("/lots/{id}", response_model=LotPublic, tags=["Inventory"])
def get_lot(id: UUID, session: DB):
    return catalog.public_lot(session, id)


@router.patch("/lots/{id}", response_model=LotPrivate, tags=["Inventory"])
def patch_lot(id: UUID, data: LotPatch, session: DB, organization: Manager):
    return catalog.patch_lot(session, organization, id, data)


@router.post("/lots/{id}/publish", response_model=LotPrivate, tags=["Inventory"])
def publish_lot(id: UUID, session: DB, organization: Manager):
    return catalog.lot_state(session, organization, id, "ACTIVE")


@router.post("/lots/{id}/pause", response_model=LotPrivate, tags=["Inventory"])
def pause_lot(id: UUID, session: DB, organization: Manager):
    return catalog.lot_state(session, organization, id, "PAUSED")


@router.post("/requirements", response_model=RequirementPublic, status_code=201, tags=["Requirements"])
def create_requirement(data: RequirementCreate, session: DB, organization: Manager):
    return service.create_requirement(session, organization, data)


@router.get("/requirements", response_model=list[RequirementPublic], tags=["Requirements"])
def list_requirements(session: DB, limit: Limit = 50, offset: Offset = 0):
    return catalog.public_requirements(session, limit, offset)


@router.get("/requirements/{id}", response_model=RequirementPublic, tags=["Requirements"])
def get_requirement(id: UUID, session: DB):
    return catalog.public_requirement(session, id)


@router.patch("/requirements/{id}", response_model=RequirementPublic, tags=["Requirements"])
def patch_requirement(id: UUID, data: RequirementPatch, session: DB, organization: Manager):
    return catalog.patch_requirement(session, organization, id, data)


@router.post("/requirements/{id}/pause", response_model=RequirementPublic, tags=["Requirements"])
def pause_requirement(id: UUID, session: DB, organization: Manager):
    return catalog.pause_requirement(session, organization, id)


@router.get("/requirements/{id}/matches", response_model=list[LotMatch], tags=["Matching"])
def requirement_matches(id: UUID, session: DB, organization: Org):
    if service.require(session, BuyerRequirement, id).buyer_org_id != organization.id:
        raise HTTPException(403, "Only the requirement organization can view its matches.")
    return service.requirement_matches(session, id)


@router.get("/lots/{id}/matching-buyers", response_model=list[BuyerMatch], tags=["Matching"])
def matching_buyers(id: UUID, session: DB, organization: Org):
    if service.require(session, SurplusLot, id).seller_org_id != organization.id:
        raise HTTPException(403, "Only the lot seller can view matching buyers.")
    return service.matching_buyers(session, id)


@router.post("/lots/{id}/offers", response_model=OfferResponse, status_code=201, tags=["Offers"])
def create_offer(id: UUID, data: OfferCreate, session: DB, organization: Manager):
    return service.make_offer(session, organization, id, data)


@router.get("/offers", response_model=list[OfferResponse], tags=["Offers"])
def list_offers(session: DB, organization: Org, limit: Limit = 50, offset: Offset = 0):
    return service.list_offers(session, organization, limit, offset)


@router.post("/offers/{id}/respond", response_model=RespondResponse, tags=["Offers"])
def respond(id: UUID, data: Respond, session: DB, organization: Manager, actor: Actor):
    return service.respond(session, organization, id, data.action, actor.user.id)


@router.get("/deals/{id}", response_model=DealResponse, tags=["Deals"])
def get_deal(id: UUID, session: DB, organization: Org):
    return service.get_deal(session, organization, id)


@router.post("/deals/{id}/checkout", response_model=CheckoutResponse, tags=["Demo checkout"], summary="DEMO ONLY: create a pending mock payment")
def checkout(id: UUID, session: DB, organization: Manager, actor: Actor):
    return service.checkout(session, organization, id, actor.user.id)
