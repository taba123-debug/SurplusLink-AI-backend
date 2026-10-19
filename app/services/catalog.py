"""Organization and listing queries/publication rules."""
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.models import Organization, SurplusLot, BuyerRequirement, Deal, Offer, OrganizationMembership, User
from app.schemas.marketplace import LotCreate, RequirementCreate
from app.services.marketplace import require, now, today, eligible


def public_organizations(session, limit=50, offset=0):
    return session.scalars(select(Organization).where(Organization.is_active.is_(True)).order_by(Organization.name, Organization.id).limit(limit).offset(offset)).all()


def demo_identities(session):
    from app.seed import demo_id
    return session.execute(select(User.id.label("user_id"), User.full_name.label("user_name"),
        Organization.id.label("organization_id"), Organization.name.label("organization_name"), OrganizationMembership.role)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(User.id.in_([demo_id(f"user-{i}") for i in range(5)]),
            Organization.id.in_([demo_id(f"org-{i}") for i in range(5)]), User.is_active.is_(True),
            Organization.is_active.is_(True), OrganizationMembership.is_active.is_(True))
        .order_by(Organization.name)).mappings().all()


def public_organization(session, key):
    organization = require(session, Organization, key)
    if not organization.is_active:
        raise HTTPException(404, "Organization not found.")
    return organization


def eligible_lots_query():
    return select(SurplusLot).join(Organization, Organization.id == SurplusLot.seller_org_id).where(
        Organization.is_active.is_(True), SurplusLot.status == "ACTIVE", SurplusLot.resale_confirmed.is_(True),
        SurplusLot.information_confirmed.is_(True), SurplusLot.packaging_type == "sealed",
        SurplusLot.expiry_date > today(), SurplusLot.pickup_deadline > now(),
        SurplusLot.quantity_total - SurplusLot.quantity_reserved - SurplusLot.quantity_sold >= SurplusLot.minimum_order_quantity)


def public_lots(session, limit=50, offset=0):
    return session.scalars(eligible_lots_query().order_by(SurplusLot.created_at.desc(), SurplusLot.id).limit(limit).offset(offset)).all()


def public_lot(session, key):
    lot = session.scalar(eligible_lots_query().where(SurplusLot.id == key))
    if lot is None:
        raise HTTPException(404, "Eligible public inventory not found.")
    return lot


def own_lots(session, organization, limit, offset):
    return session.scalars(select(SurplusLot).where(SurplusLot.seller_org_id == organization.id).order_by(SurplusLot.created_at.desc(), SurplusLot.id).limit(limit).offset(offset)).all()


def owned(session, model, key, organization, owner_field):
    item = session.scalar(select(model).where(model.id == key).with_for_update().execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(404, "Resource not found.")
    if getattr(item, owner_field) != organization.id:
        raise HTTPException(403, "Resource belongs to another organization.")
    return item


def validate_lot(data):
    from app.services.marketplace import validate_lot_dates
    validate_lot_dates(data)


def patch_lot(session, organization, key, patch):
    lot = owned(session, SurplusLot, key, organization, "seller_org_id")
    if lot.quantity_reserved or lot.quantity_sold:
        raise HTTPException(409, "Inventory with reserved or sold units cannot be edited.")
    if lot.status not in ("DRAFT", "ACTIVE", "PAUSED"):
        raise HTTPException(409, "Listing cannot be edited in its current state.")
    values = {name: getattr(lot, name) for name in LotCreate.model_fields}
    values["status"] = "ACTIVE" if lot.status == "ACTIVE" else "DRAFT"
    values.update(patch.model_dump(exclude_unset=True))
    try:
        data = LotCreate.model_validate(values)
    except ValidationError:
        raise HTTPException(422, "Updated inventory fields are invalid or inconsistent.") from None
    validate_lot(data)
    for name in patch.model_fields_set:
        setattr(lot, name, getattr(data, name))
    session.commit()
    return lot


def lot_state(session, organization, key, status):
    lot = owned(session, SurplusLot, key, organization, "seller_org_id")
    if lot.status not in ("DRAFT", "ACTIVE", "PAUSED"):
        raise HTTPException(409, "Listing cannot transition in its current state.")
    if status == "ACTIVE":
        values = {name: getattr(lot, name) for name in LotCreate.model_fields}
        values["status"] = "ACTIVE"
        try:
            data = LotCreate.model_validate(values)
        except ValidationError:
            raise HTTPException(422, "Complete confirmed inventory is required for publication.") from None
        validate_lot(data)
        if lot.available_quantity < lot.minimum_order_quantity:
            raise HTTPException(409, "Insufficient inventory for publication.")
    lot.status = status
    session.commit()
    return lot


def public_requirements(session, limit=50, offset=0):
    return session.scalars(select(BuyerRequirement).join(Organization).where(Organization.is_active.is_(True),
        BuyerRequirement.status == "ACTIVE").order_by(BuyerRequirement.created_at.desc(), BuyerRequirement.id).limit(limit).offset(offset)).all()


def public_requirement(session, key):
    item = require(session, BuyerRequirement, key)
    if item.status != "ACTIVE" or not require(session, Organization, item.buyer_org_id).is_active:
        raise HTTPException(404, "Active requirement not found.")
    return item


def patch_requirement(session, organization, key, patch):
    item = owned(session, BuyerRequirement, key, organization, "buyer_org_id")
    if item.status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(409, "Requirement cannot be edited in its current state.")
    if session.scalar(select(Deal.id).join(Offer, Offer.id == Deal.offer_id).where(Offer.requirement_id == key, Deal.status.in_(["AWAITING_PAYMENT", "PAID", "COMPLETED"]))):
        raise HTTPException(409, "A requirement linked to an accepted deal cannot be edited.")
    values = {name: getattr(item, name) for name in RequirementCreate.model_fields}
    values.update(patch.model_dump(exclude_unset=True))
    try:
        data = RequirementCreate.model_validate(values)
    except ValidationError:
        raise HTTPException(422, "Updated requirement fields are invalid.") from None
    for name in patch.model_fields_set:
        setattr(item, name, getattr(data, name))
    session.commit()
    return item


def pause_requirement(session, organization, key):
    item = owned(session, BuyerRequirement, key, organization, "buyer_org_id")
    if item.status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(409, "Requirement cannot be paused.")
    item.status = "PAUSED"
    session.commit()
    return item
