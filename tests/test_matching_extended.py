from datetime import timedelta

from app.models import SurplusLot, BuyerRequirement, Organization
from app.seed import demo_id
from app.services.marketplace import match_details, today
from test_marketplace import BUYER, SELLER


def test_scoring_financial_breakdown_and_reserve_independence(market_client, db):
    path = f"/api/v1/requirements/{demo_id('requirement-0')}/matches"
    response = market_client.get(path, headers=BUYER)
    assert response.status_code == 200
    item = next(x for x in response.json() if x["lot_id"] == str(demo_id("lot-0")))
    assert item["match_type"] == "NEGOTIABLE" and item["match_score"] == 80
    assert item["estimated_subtotal_minor"] == 2100000 and item["estimated_buyer_fee_minor"] == 42000
    db.get(SurplusLot, demo_id("lot-0")).min_unit_price_minor = 13999
    db.flush()
    after = next(x for x in market_client.get(path, headers=BUYER).json() if x["lot_id"] == item["lot_id"])
    assert after == item
    assert "min_unit_price_minor" not in response.text and "contact_email" not in response.text


def test_same_organization_and_expired_lot_are_excluded(db):
    lot = db.get(SurplusLot, demo_id("lot-0"))
    requirement = db.get(BuyerRequirement, demo_id("requirement-0"))
    requirement.buyer_org_id = lot.seller_org_id
    assert match_details(lot, requirement) is None
    requirement.buyer_org_id = demo_id("org-2")
    lot.expiry_date = today() - timedelta(days=1)
    assert match_details(lot, requirement) is None


def test_matching_requires_resource_ownership(market_client):
    assert market_client.get(f"/api/v1/lots/{demo_id('lot-0')}/matching-buyers", headers=BUYER).status_code == 403
    assert market_client.get(f"/api/v1/requirements/{demo_id('requirement-0')}/matches", headers=SELLER).status_code == 403
