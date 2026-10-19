from uuid import UUID

from fastapi import APIRouter

from app.api.v1.marketplace import DB, Org, Limit, Offset
from app.schemas.marketplace import DemoOrganization, OrganizationPrivate
from app.services import catalog

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.get("", response_model=list[DemoOrganization])
def organizations(session: DB, limit: Limit = 50, offset: Offset = 0):
    return catalog.public_organizations(session, limit, offset)


@router.get("/me", response_model=OrganizationPrivate)
def current_organization(organization: Org):
    return organization


@router.get("/{id}", response_model=DemoOrganization)
def organization(id: UUID, session: DB):
    return catalog.public_organization(session, id)
