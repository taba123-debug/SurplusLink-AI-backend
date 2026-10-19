from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, DBAPIError

from app.models import SurplusLot, BuyerRequirement, Offer, Deal, Payment, DealEvent
from app.seed import demo_id
from app.services.marketplace import now, today, fee, monetary_snapshot, match_details

SELLER = {"X-Demo-Org-ID": str(demo_id("org-0")), "X-Demo-User-ID": str(demo_id("user-0"))}
BUYER = {"X-Demo-Org-ID": str(demo_id("org-2")), "X-Demo-User-ID": str(demo_id("user-2"))}


def lot_payload():
    return dict(product_name="Sealed biscuits", category="Biscuit", description="Sealed packs",
        quantity_total=200, unit="packs", asking_unit_price_minor=14000, min_unit_price_minor=11000,
        minimum_order_quantity=10, packaging_type="sealed", storage_type="ambient", expiry_date=str(today() + timedelta(days=45)),
        city="Lahore", pickup_area="Gulberg", pickup_address="PRIVATE LOCATION", original_description="SECRET RESERVE 110",
        pickup_deadline=(now() + timedelta(days=2)).isoformat(), resale_confirmed=True, information_confirmed=True)


def offer_payload(quantity=150):
    return dict(quantity=quantity, offered_unit_price_minor=12000, expires_at=(now() + timedelta(hours=1)).isoformat())


def make_deal(client):
    lot = client.post("/api/v1/lots", json=lot_payload(), headers=SELLER)
    assert lot.status_code == 201, lot.text
    offer = client.post(f"/api/v1/lots/{lot.json()['id']}/offers", json=offer_payload(), headers=BUYER)
    assert offer.status_code == 201, offer.text
    result = client.post(f"/api/v1/offers/{offer.json()['id']}/respond", json={"action": "ACCEPT"}, headers=SELLER)
    assert result.status_code == 200, result.text
    return lot.json(), offer.json(), result.json()["deal"]


def test_create_read_private_fields_and_context(market_client):
    client = market_client
    assert client.post("/api/v1/lots", json=lot_payload()).status_code == 422
    result = client.post("/api/v1/lots", json=lot_payload(), headers=SELLER)
    assert result.status_code == 201, result.text
    data = result.json()
    assert data["category"] == "biscuits" and data["unit"] == "pack"
    assert data["available_quantity"] == 200
    for path in ("/api/v1/lots", f"/api/v1/lots/{data['id']}"):
        response = client.get(path)
        assert response.status_code == 200
        assert "min_unit_price_minor" not in response.text
        assert "pickup_address" not in response.text
        assert "SECRET RESERVE" not in response.text
        assert "PRIVATE LOCATION" not in response.text
    assert client.get(f"/api/v1/lots/{uuid4()}").status_code == 404
    invalid = lot_payload() | {"resale_confirmed": False}
    assert client.post("/api/v1/lots", json=invalid, headers=SELLER).status_code == 422


def test_requirement_and_bidirectional_matching(market_client):
    client = market_client
    response = client.post("/api/v1/requirements", headers=BUYER, json=dict(title="Need biscuits",
        original_description="150 biscuit packs under Rs 20000", category="biscuits", required_quantity=150,
        unit="pack", max_total_budget_minor=2000000, min_shelf_life_days=30, city="Lahore"))
    assert response.status_code == 201, response.text
    key = response.json()["id"]
    matches = client.get(f"/api/v1/requirements/{key}/matches", headers=BUYER)
    assert matches.status_code == 200, matches.text
    assert matches.json()[0]["match_type"] == "NEGOTIABLE"
    assert matches.json()[0]["estimated_buyer_total_minor"] == 2142000
    lot = matches.json()[0]["lot"]["id"]
    seller_org = client.get(f"/api/v1/lots/{lot}").json()["seller_org_id"]
    seller_user = demo_id("user-0") if seller_org == str(demo_id("org-0")) else demo_id("user-1")
    reverse = client.get(f"/api/v1/lots/{lot}/matching-buyers", headers={"X-Demo-Org-ID":seller_org,"X-Demo-User-ID":str(seller_user)})
    assert key in [item["requirement"]["id"] for item in reverse.json()]
    assert "min_unit_price_minor" not in matches.text
    assert client.get(f"/api/v1/requirements/{key}").status_code == 200
    assert client.get("/api/v1/requirements").status_code == 200


@pytest.mark.parametrize("field,value", [("category", "bread"), ("unit", "tray"), ("city", "karachi"),
    ("required_quantity", 1000), ("required_quantity", 1), ("min_shelf_life_days", 100), ("status", "CLOSED")])
def test_matching_filters(db, field, value):
    lot = db.get(SurplusLot, demo_id("lot-0"))
    requirement = db.get(BuyerRequirement, demo_id("requirement-0"))
    setattr(requirement, field, value)
    assert match_details(lot, requirement) is None


def test_matching_direct_and_expiry(db):
    lot = db.get(SurplusLot, demo_id("lot-0"))
    requirement = db.get(BuyerRequirement, demo_id("requirement-1"))
    assert match_details(lot, requirement)["match_type"] == "DIRECT"
    lot.pickup_deadline = now() - timedelta(minutes=1)
    assert match_details(lot, requirement) is None


def test_offer_accept_fees_and_checkout_are_idempotent(market_client, db):
    client = market_client
    lot, offer, deal = make_deal(client)
    assert deal["subtotal_minor"] == 1800000
    assert deal["buyer_fee_minor"] == deal["seller_fee_minor"] == 36000
    assert deal["buyer_total_minor"] == 1836000
    assert deal["seller_net_minor"] == 1764000
    again = client.post(f"/api/v1/offers/{offer['id']}/respond", json={"action": "ACCEPT"}, headers=SELLER)
    assert again.json()["deal"]["id"] == deal["id"]
    assert client.get(f"/api/v1/lots/{lot['id']}").json()["available_quantity"] == 50
    assert client.get("/api/v1/offers", headers=BUYER).status_code == 200
    assert client.get(f"/api/v1/deals/{deal['id']}", headers={"X-Demo-Org-ID": str(demo_id("org-4")), "X-Demo-User-ID": str(demo_id("user-4"))}).status_code == 403
    first = client.post(f"/api/v1/deals/{deal['id']}/checkout", headers=BUYER)
    second = client.post(f"/api/v1/deals/{deal['id']}/checkout", headers=BUYER)
    assert first.status_code == 200, first.text
    assert first.json()["simulated"] is True
    assert second.json()["payment"]["id"] == first.json()["payment"]["id"]
    assert first.json()["payment"]["status"] == "PENDING"
    paid = client.post(f"/api/v1/payments/mock/{first.json()['payment_id']}/succeed", headers=BUYER)
    assert paid.status_code == 200, paid.text
    assert client.post(f"/api/v1/payments/mock/{first.json()['payment_id']}/succeed", headers=BUYER).status_code == 200
    assert db.scalar(select(func.count()).select_from(Payment).where(Payment.deal_id == UUID(deal['id']))) == 1
    assert paid.json()["deal"]["status"] == "PAID"
    assert client.get(f"/api/v1/lots/{lot['id']}").json()["quantity_sold"] == 0


def test_reject_and_wrong_party(market_client):
    client = market_client
    key = str(demo_id("lot-0"))
    response = client.post(f"/api/v1/lots/{key}/offers", json=offer_payload(), headers=BUYER)
    offer = response.json()["id"]
    assert client.post(f"/api/v1/offers/{offer}/respond", json={"action": "ACCEPT"}, headers=BUYER).status_code == 403
    assert client.post(f"/api/v1/offers/{offer}/respond", json={"action": "REJECT"}, headers=SELLER).json()["offer"]["status"] == "REJECTED"


def test_snapshots_history_and_unique_offer(db, market_client):
    _, _, deal = make_deal(market_client)
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(text("UPDATE deals SET agreed_unit_price_minor = agreed_unit_price_minor + 1 WHERE id = :id"), {"id": deal["id"]})
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(text("UPDATE deal_events SET event_type = 'REWRITE' WHERE deal_id = :id"), {"id": deal["id"]})
    with pytest.raises(IntegrityError), db.begin_nested():
        values = {c.name: getattr(db.get(Deal, UUID(deal['id'])), c.name) for c in Deal.__table__.columns if c.name not in ('id','created_at','updated_at')}
        db.add(Deal(**values))
        db.flush()


def test_fee_rounding():
    assert fee(25) == 1
    assert fee(24) == 0
    assert monetary_snapshot(150, 12000)["buyer_total_minor"] == 1836000
