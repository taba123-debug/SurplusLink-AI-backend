from fastapi import HTTPException
from sqlalchemy import select, case

from app.models import Payment
from app.services.marketplace import get_deal, now, require
from app.services.deal_service import lock_deal, ensure_payable, event


def latest_payment(session, organization, key):
    get_deal(session, organization, key)
    payment = session.scalar(select(Payment).where(Payment.deal_id == key).order_by(
        case((Payment.status == "PENDING", 0), (Payment.status == "SUCCEEDED", 1), else_=2),
        Payment.created_at.desc(), Payment.id.desc()))
    if payment is None:
        raise HTTPException(404, "No payment attempt exists.")
    return payment


def checkout(session, organization, key, actor=None):
    initial = get_deal(session, organization, key)
    if organization.id != initial.buyer_org_id:
        raise HTTPException(403, "Only the buyer can start mock checkout.")
    deal, lot = lock_deal(session, key)
    if deal.status == "CANCELLED":
        raise HTTPException(409, "A cancelled deal cannot be paid.")
    existing = session.scalar(select(Payment).where(Payment.deal_id == key, Payment.status == "SUCCEEDED"))
    if existing:
        session.commit()
        return {"payment":existing, "deal":deal}
    ensure_payable(deal, lot)
    payment = session.scalar(select(Payment).where(Payment.deal_id == key, Payment.status == "PENDING"))
    if payment is None:
        payment = Payment(deal_id=key, amount_minor=deal.buyer_total_minor, currency=deal.currency, provider="MOCK", status="PENDING")
        session.add(payment)
        event(session, deal, "MOCK_CHECKOUT_CREATED", actor, amount_minor=deal.buyer_total_minor)
    session.commit()
    return {"payment":payment, "deal":deal}


def resolve(session, organization, payment_id, success, actor=None):
    initial = require(session, Payment, payment_id)
    get_deal(session, organization, initial.deal_id)
    deal, lot = lock_deal(session, initial.deal_id)
    if organization.id != deal.buyer_org_id:
        raise HTTPException(403, "Only the buyer owner/manager can simulate a payment result.")
    payment = session.scalar(select(Payment).where(Payment.id == payment_id).with_for_update().execution_options(populate_existing=True))
    target = "SUCCEEDED" if success else "FAILED"
    if payment.status == target:
        session.commit()
        return {"payment":payment, "deal":deal}
    if payment.status != "PENDING":
        raise HTTPException(409, "Payment has already reached a different terminal state.")
    ensure_payable(deal, lot)
    if payment.provider != "MOCK" or payment.amount_minor != deal.buyer_total_minor or payment.currency != deal.currency:
        raise HTTPException(409, "Payment attempt does not match this deal.")
    payment.status = target
    if success:
        payment.paid_at = now()
        deal.status = "PAID"
    event(session, deal, "MOCK_PAYMENT_" + target, actor, payment_id=str(payment.id), amount_minor=payment.amount_minor)
    session.commit()
    return {"payment":payment, "deal":deal}
