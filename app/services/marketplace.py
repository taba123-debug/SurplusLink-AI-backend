from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.models import Organization, SurplusLot, BuyerRequirement, Offer, Deal, Payment, DealEvent


def now():
    return datetime.now(timezone.utc)


def today():
    return now().astimezone(ZoneInfo("Asia/Karachi")).date()


def require(session, model, key):
    obj = session.get(model, key)
    if obj is None:
        raise HTTPException(404, "Resource not found.")
    return obj


def fee(subtotal: int, bps: int = 200) -> int:
    """Round nonnegative paisa half up, using integer arithmetic only."""
    return (subtotal * bps + 5000) // 10000


def monetary_snapshot(quantity, unit_price):
    subtotal = quantity * unit_price
    buyer_fee = fee(subtotal)
    seller_fee = fee(subtotal)
    return dict(subtotal_minor=subtotal, buyer_fee_bps=200, seller_fee_bps=200,
                buyer_fee_minor=buyer_fee, seller_fee_minor=seller_fee,
                buyer_total_minor=subtotal + buyer_fee, seller_net_minor=subtotal - seller_fee)


def eligible(lot):
    return (lot.status == "ACTIVE" and lot.resale_confirmed and lot.information_confirmed
            and lot.packaging_type == "sealed" and lot.expiry_date > today() and lot.pickup_deadline > now())


def validate_lot_dates(data):
    if data.expiry_date <= today() or data.pickup_deadline <= now():
        raise HTTPException(422, "Expiry and pickup deadline must be in the future.")
    if data.pickup_deadline.astimezone(ZoneInfo("Asia/Karachi")).date() > data.expiry_date:
        raise HTTPException(422, "Pickup deadline must not be after expiry.")
    if data.manufacture_date and data.manufacture_date > today():
        raise HTTPException(422, "Manufacture date must not be in the future.")


def create_lot(session, organization, data):
    validate_lot_dates(data)
    lot = SurplusLot(seller_org_id=organization.id, **data.model_dump())
    session.add(lot)
    session.commit()
    return lot


def create_requirement(session, organization, data):
    item = BuyerRequirement(buyer_org_id=organization.id, **data.model_dump())
    session.add(item)
    session.commit()
    return item


def match_details(lot, requirement):
    if (not eligible(lot) or requirement.status != "ACTIVE" or lot.seller_org_id == requirement.buyer_org_id
        or lot.category != requirement.category or lot.unit != requirement.unit or lot.city != requirement.city
        or lot.available_quantity < requirement.required_quantity
        or requirement.required_quantity < lot.minimum_order_quantity
        or (lot.expiry_date - today()).days < requirement.min_shelf_life_days):
        return None
    subtotal = requirement.required_quantity * lot.asking_unit_price_minor
    buyer_fee = fee(subtotal)
    estimated = subtotal + buyer_fee
    direct = estimated <= requirement.max_total_budget_minor
    return {"match_type": "DIRECT" if direct else "NEGOTIABLE", "match_score": 100 if direct else 80,
            "estimated_subtotal_minor": subtotal, "estimated_buyer_fee_minor": buyer_fee, "estimated_buyer_total_minor": estimated,
            "reasons": ["Exact category, unit and city match.", "Requested quantity is available and meets the minimum order.",
                        "Expiry meets the requested shelf life; pickup deadline is still open.",
                        "Asking price plus 2% buyer fee fits the budget." if direct else
                        "Asking price plus buyer fee exceeds budget; seller acceptance is not guaranteed."]}


def requirement_matches(session, key):
    requirement = require(session, BuyerRequirement, key)
    if not require(session, Organization, requirement.buyer_org_id).is_active:
        return []
    lots = session.scalars(select(SurplusLot).join(Organization, Organization.id == SurplusLot.seller_org_id).where(Organization.is_active.is_(True), SurplusLot.category == requirement.category,
        SurplusLot.unit == requirement.unit, SurplusLot.city == requirement.city, SurplusLot.status == "ACTIVE").order_by(SurplusLot.created_at, SurplusLot.id))
    return sorted([{"lot_id": lot.id, "lot": lot, **details} for lot in lots if (details := match_details(lot, requirement))], key=lambda item: (-item["match_score"], item["estimated_buyer_total_minor"], str(item["lot_id"])))


def matching_buyers(session, key):
    lot = require(session, SurplusLot, key)
    if not require(session, Organization, lot.seller_org_id).is_active:
        return []
    requirements = session.scalars(select(BuyerRequirement).join(Organization).where(Organization.is_active.is_(True), BuyerRequirement.category == lot.category,
        BuyerRequirement.unit == lot.unit, BuyerRequirement.city == lot.city, BuyerRequirement.status == "ACTIVE").order_by(BuyerRequirement.created_at, BuyerRequirement.id))
    return sorted([{"requirement_id": item.id, "requirement": item, **details} for item in requirements if (details := match_details(lot, item))], key=lambda item: (-item["match_score"], str(item["requirement_id"])))


def make_offer(session, organization, lot_id, data):
    from datetime import timedelta
    lot = require(session, SurplusLot, lot_id)
    if organization.id == lot.seller_org_id:
        raise HTTPException(422, "An organization cannot buy its own inventory.")
    if not eligible(lot) or data.quantity > lot.available_quantity or data.quantity < lot.minimum_order_quantity:
        raise HTTPException(409, "Inventory is unavailable for this quantity.")
    expiry = data.expires_at or min(now() + timedelta(hours=24), lot.pickup_deadline)
    if expiry <= now() or expiry > lot.pickup_deadline:
        raise HTTPException(422, "Offer expiry must be in the future and no later than pickup.")
    if data.requirement_id:
        requirement = require(session, BuyerRequirement, data.requirement_id)
        if requirement.buyer_org_id != organization.id:
            raise HTTPException(403, "Requirement belongs to another organization.")
        if not match_details(lot, requirement) or data.quantity != requirement.required_quantity:
            raise HTTPException(422, "Offer does not satisfy its linked requirement.")
        if monetary_snapshot(data.quantity, data.offered_unit_price_minor)["buyer_total_minor"] > requirement.max_total_budget_minor:
            raise HTTPException(422, "Offer including buyer fee exceeds the requirement budget.")
    offer = Offer(lot_id=lot_id, buyer_org_id=organization.id, **(data.model_dump() | {"expires_at": expiry}))
    session.add(offer)
    session.commit()
    return offer


def list_offers(session, organization, limit, offset):
    return session.scalars(select(Offer).join(SurplusLot).where(or_(Offer.buyer_org_id == organization.id,
        SurplusLot.seller_org_id == organization.id)).order_by(Offer.created_at.desc(), Offer.id).limit(limit).offset(offset)).all()


def respond(session, organization, offer_id, action, actor_user_id=None):
    # The dependency's org lookup starts this request's transaction. Lock lot first
    # everywhere, then offer/deal, to serialize stock changes without deadlocks.
    original = require(session, Offer, offer_id)
    lot = session.scalar(select(SurplusLot).where(SurplusLot.id == original.lot_id).with_for_update().execution_options(populate_existing=True))
    offer = session.scalar(select(Offer).where(Offer.id == offer_id).with_for_update().execution_options(populate_existing=True))
    if lot.seller_org_id != organization.id:
        raise HTTPException(403, "Only the lot seller can respond.")
    if offer.status == "ACCEPTED" and action == "ACCEPT":
        deal = session.scalar(select(Deal).where(Deal.offer_id == offer.id))
        session.commit()
        return {"offer": offer, "deal": deal}
    if offer.status != "PENDING" or offer.expires_at <= now():
        raise HTTPException(409, "Offer is no longer pending or has expired.")
    if action == "REJECT":
        offer.status = "REJECTED"
        session.commit()
        return {"offer": offer, "deal": None}
    if not eligible(lot) or lot.available_quantity < offer.quantity or offer.quantity < lot.minimum_order_quantity:
        raise HTTPException(409, "Insufficient eligible inventory.")
    if not require(session, Organization, offer.buyer_org_id).is_active:
        raise HTTPException(409, "Offer is not eligible for acceptance.")
    if offer.offered_unit_price_minor < lot.min_unit_price_minor:
        raise HTTPException(409, "Offer cannot be accepted under the current seller policy.")
    if offer.requirement_id:
        requirement = session.scalar(select(BuyerRequirement).where(BuyerRequirement.id == offer.requirement_id).with_for_update())
        if (not match_details(lot, requirement) or offer.quantity != requirement.required_quantity
            or monetary_snapshot(offer.quantity, offer.offered_unit_price_minor)["buyer_total_minor"] > requirement.max_total_budget_minor):
            raise HTTPException(409, "Linked requirement is no longer eligible.")
    lot.quantity_reserved += offer.quantity
    offer.status = "ACCEPTED"
    deal = Deal(offer_id=offer.id, lot_id=lot.id, buyer_org_id=offer.buyer_org_id,
        seller_org_id=lot.seller_org_id, quantity=offer.quantity, agreed_unit_price_minor=offer.offered_unit_price_minor,
        **monetary_snapshot(offer.quantity, offer.offered_unit_price_minor))
    session.add(deal)
    session.flush()
    session.add(DealEvent(deal_id=deal.id, actor_user_id=actor_user_id, event_type="OFFER_ACCEPTED", event_metadata={"simulated_marketplace": True}))
    session.commit()
    return {"offer": offer, "deal": deal}


def get_deal(session, organization, key):
    deal = require(session, Deal, key)
    if organization.id not in (deal.buyer_org_id, deal.seller_org_id):
        raise HTTPException(403, "Deal belongs to other organizations.")
    return deal


def checkout(session, organization, key, actor_user_id=None):
    from app.services.payment_service import checkout as create_attempt
    return create_attempt(session, organization, key, actor_user_id)
