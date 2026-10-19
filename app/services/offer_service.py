from fastapi import HTTPException
from sqlalchemy import select

from app.models import Offer, SurplusLot
from app.services.marketplace import require, now


def get_offer(session, organization, key):
    offer = require(session, Offer, key)
    lot = require(session, SurplusLot, offer.lot_id)
    if organization.id not in (offer.buyer_org_id, lot.seller_org_id):
        raise HTTPException(403, "Offer belongs to other organizations.")
    return offer


def withdraw(session, organization, key):
    initial = get_offer(session, organization, key)
    session.scalar(select(SurplusLot).where(SurplusLot.id == initial.lot_id).with_for_update())
    offer = session.scalar(select(Offer).where(Offer.id == key).with_for_update().execution_options(populate_existing=True))
    if offer.buyer_org_id != organization.id:
        raise HTTPException(403, "Only the offer buyer can withdraw it.")
    if offer.status != "PENDING" or offer.expires_at <= now():
        raise HTTPException(409, "Only an unexpired pending offer can be withdrawn.")
    offer.status = "WITHDRAWN"
    session.commit()
    return offer
