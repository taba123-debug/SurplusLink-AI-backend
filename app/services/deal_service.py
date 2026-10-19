from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.models import Deal, SurplusLot, Offer, BuyerRequirement, Payment, DealEvent
from app.services.marketplace import get_deal, now, today

PAYMENT_WINDOW = timedelta(hours=1)


def payment_deadline(deal):
    return deal.created_at + PAYMENT_WINDOW


def event(session, deal, kind, actor=None, **metadata):
    session.add(DealEvent(deal_id=deal.id, actor_user_id=actor, event_type=kind,
                          event_metadata={"simulated":True, **metadata}))


def lock_deal(session, key):
    initial = session.get(Deal, key)
    if initial is None:
        raise HTTPException(404, "Deal not found.")
    lot = session.scalar(select(SurplusLot).where(SurplusLot.id == initial.lot_id).with_for_update().execution_options(populate_existing=True))
    deal = session.scalar(select(Deal).where(Deal.id == key).with_for_update().execution_options(populate_existing=True))
    return deal, lot


def list_deals(session, organization, limit, offset):
    return session.scalars(select(Deal).where(or_(Deal.buyer_org_id == organization.id,
        Deal.seller_org_id == organization.id)).order_by(Deal.created_at.desc(), Deal.id).limit(limit).offset(offset)).all()


def ensure_payable(deal, lot):
    if deal.status != "AWAITING_PAYMENT":
        raise HTTPException(409, "Deal is not awaiting payment.")
    if payment_deadline(deal) <= now() or lot.pickup_deadline <= now() or lot.expiry_date <= today():
        raise HTTPException(409, "Payment or collection eligibility has expired; cancel the unpaid deal.")


def cancel_locked(session, deal, lot, actor=None, reason="CANCELLED"):
    # Paid cancellation needs a refund workflow, deliberately outside this demo.
    if deal.status != "AWAITING_PAYMENT":
        raise HTTPException(409, "Only unpaid deals can be cancelled; paid deals require a refund workflow.")
    if lot.quantity_reserved < deal.quantity:
        raise HTTPException(409, "Inventory reservation is inconsistent.")
    lot.quantity_reserved -= deal.quantity
    deal.status = "CANCELLED"
    for payment in session.scalars(select(Payment).where(Payment.deal_id == deal.id, Payment.status == "PENDING").with_for_update()):
        payment.status = "FAILED"
    event(session, deal, reason, actor)


def cancel(session, organization, key, actor=None):
    get_deal(session, organization, key)
    deal, lot = lock_deal(session, key)
    cancel_locked(session, deal, lot, actor)
    session.commit()
    return deal


def complete(session, organization, key, actor=None):
    get_deal(session, organization, key)
    deal, lot = lock_deal(session, key)
    if organization.id != deal.seller_org_id:
        raise HTTPException(403, "Only the seller owner/manager can confirm physical collection.")
    if deal.status != "PAID":
        raise HTTPException(409, "Only a paid, uncompleted deal can be collected.")
    if not session.scalar(select(Payment.id).where(Payment.deal_id == key, Payment.status == "SUCCEEDED")):
        raise HTTPException(409, "No successful simulated payment exists.")
    if lot.expiry_date <= today() or lot.pickup_deadline <= now():
        raise HTTPException(409, "Expired inventory or overdue pickup cannot be collected.")
    if lot.quantity_reserved < deal.quantity:
        raise HTTPException(409, "Inventory reservation is inconsistent.")
    lot.quantity_reserved -= deal.quantity
    lot.quantity_sold += deal.quantity
    if lot.quantity_sold == lot.quantity_total:
        lot.status = "SOLD_OUT"
    deal.status = "COMPLETED"
    offer = session.get(Offer, deal.offer_id)
    if offer.requirement_id:
        requirement = session.scalar(select(BuyerRequirement).where(BuyerRequirement.id == offer.requirement_id).with_for_update())
        requirement.status = "FULFILLED"
    event(session, deal, "COLLECTION_CONFIRMED", actor, quantity=deal.quantity)
    session.commit()
    return deal


def pickup_details(session, organization, key):
    deal = get_deal(session, organization, key)
    if deal.status not in ("PAID", "COMPLETED"):
        raise HTTPException(403, "Pickup details unlock after successful simulated payment.")
    lot = session.get(SurplusLot, deal.lot_id)
    return dict(deal_id=deal.id, pickup_address=lot.pickup_address, pickup_area=lot.pickup_area, pickup_deadline=lot.pickup_deadline)


def expire_unpaid(session):
    """Explicit maintenance command, no queue, each cancellation atomic."""
    keys = session.scalars(select(Deal.id).where(Deal.status == "AWAITING_PAYMENT")).all()
    cancelled = 0
    for key in keys:
        deal, lot = lock_deal(session, key)
        if deal.status == "AWAITING_PAYMENT" and (payment_deadline(deal) <= now() or lot.pickup_deadline <= now() or lot.expiry_date <= today()):
            cancel_locked(session, deal, lot, reason="UNPAID_DEAL_EXPIRED")
            cancelled += 1
        session.commit()
    return cancelled


if __name__ == "__main__":
    from app.core.config import get_settings
    from app.db.session import create_session_factory
    settings = get_settings()
    if settings.app_env != "development" or not settings.demo_mode:
        raise SystemExit("Explicit demo cleanup is disabled outside development DEMO_MODE.")
    engine, factory = create_session_factory(settings)
    with factory() as session:
        print({"expired_unpaid_deals": expire_unpaid(session), "simulated":True})
    engine.dispose()
