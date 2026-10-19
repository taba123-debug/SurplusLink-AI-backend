from datetime import timedelta

from sqlalchemy import select

from app.models import Offer, SurplusLot
from app.seed import demo_id
from app.services.marketplace import now
from test_marketplace import SELLER, BUYER, offer_payload


def test_reserve_policy_is_confidential_and_atomic(market_client, db):
    lot = demo_id("lot-0")
    result = market_client.post(f"/api/v1/lots/{lot}/offers", headers=BUYER, json=offer_payload() | {"offered_unit_price_minor":10000})
    assert result.status_code == 201
    key = result.json()["id"]
    rejected = market_client.post(f"/api/v1/offers/{key}/respond", headers=SELLER, json={"action":"ACCEPT"})
    assert rejected.status_code == 409
    assert "11000" not in rejected.text and "reserve" not in rejected.text
    assert db.get(SurplusLot, lot).quantity_reserved == 0
    assert db.get(Offer, __import__('uuid').UUID(key)).status == "PENDING"


def test_offer_defaults_withdraw_and_expiry(market_client, db):
    client = market_client
    payload = offer_payload()
    payload.pop("expires_at")
    result = client.post(f"/api/v1/lots/{demo_id('lot-0')}/offers", headers=BUYER, json=payload)
    assert result.status_code == 201, result.text
    key = result.json()["id"]
    assert client.get(f"/api/v1/offers/{key}", headers=SELLER).status_code == 200
    assert client.post(f"/api/v1/offers/{key}/withdraw", headers=SELLER).status_code == 403
    assert client.post(f"/api/v1/offers/{key}/withdraw", headers=BUYER).json()["status"] == "WITHDRAWN"
    assert client.post(f"/api/v1/offers/{key}/respond", headers=SELLER, json={"action":"ACCEPT"}).status_code == 409
    result = client.post(f"/api/v1/lots/{demo_id('lot-0')}/offers", headers=BUYER, json=offer_payload())
    key = result.json()["id"]
    offer = db.get(Offer, __import__('uuid').UUID(key))
    offer.expires_at = now() - timedelta(seconds=1)
    db.flush()
    assert client.post(f"/api/v1/offers/{key}/respond", headers=SELLER, json={"action":"ACCEPT"}).status_code == 409
