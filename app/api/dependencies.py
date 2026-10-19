from collections.abc import Generator

from fastapi import Header, HTTPException, Request, Depends
from typing import Annotated
from uuid import UUID
from sqlalchemy.orm import Session


def get_db(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        # close rolls back uncommitted work; services explicitly commit transactions.
        yield session


def require_demo(request: Request):
    settings = request.app.state.settings
    if not settings.demo_mode or settings.app_env != "development":
        raise HTTPException(403, "Demo marketplace access is disabled.")


def get_identity(request: Request, session: Annotated[Session, Depends(get_db)],
                 organization_id: Annotated[UUID, Header(alias="X-Demo-Org-ID", description="Development-only active organization selection.")],
                 user_id: Annotated[UUID, Header(alias="X-Demo-User-ID", description="Development-only fictional user selection; not production authentication.")]):
    from sqlalchemy import select
    from app.models import Organization, OrganizationMembership, User
    from app.core.security import DemoIdentity
    from app.seed import demo_id
    require_demo(request)
    if user_id not in {demo_id(f"user-{i}") for i in range(5)} or organization_id not in {demo_id(f"org-{i}") for i in range(5)}:
        raise HTTPException(403, "Only the fictional seeded demo identities may be selected.")
    organization = session.get(Organization, organization_id)
    user = session.get(User, user_id)
    membership = session.scalar(select(OrganizationMembership).where(
        OrganizationMembership.user_id == user_id, OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.is_active.is_(True)))
    if not organization or not organization.is_active or not user or not user.is_active or not membership:
        raise HTTPException(403, "Active demo user membership is required.")
    return DemoIdentity(user, organization, membership)


def get_demo_org(identity=Depends(get_identity)):
    return identity.organization


def get_manager_org(identity=Depends(get_identity)):
    return identity.require_manager()
