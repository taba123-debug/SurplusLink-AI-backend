from datetime import timedelta

from app.models import OrganizationMembership, User, Organization, SurplusLot
from app.seed import demo_id
from app.services.marketplace import now, today
from test_marketplace import SELLER, BUYER, lot_payload


def test_demo_user_membership_and_roles(market_client, db):
    client = market_client
    assert client.get("/api/v1/organizations/me", headers={"X-Demo-Org-ID": SELLER["X-Demo-Org-ID"]}).status_code == 422
    forged = SELLER | {"X-Demo-User-ID": BUYER["X-Demo-User-ID"]}
    assert client.get("/api/v1/organizations/me", headers=forged).status_code == 403
    membership = db.get(OrganizationMembership, demo_id("membership-0"))
    membership.role = "STAFF"
    db.flush()
    assert client.get("/api/v1/lots/mine", headers=SELLER).status_code == 200
    assert client.post("/api/v1/lots", headers=SELLER, json=lot_payload()).status_code == 403
    membership.is_active = False
    db.flush()
    assert client.get("/api/v1/organizations/me", headers=SELLER).status_code == 403


def test_public_and_private_organizations(market_client):
    client = market_client
    public = client.get("/api/v1/organizations")
    assert public.status_code == 200
    assert "contact_email" not in public.text and "address" not in public.text
    assert client.get(f"/api/v1/organizations/{demo_id('org-0')}").status_code == 200
    private = client.get("/api/v1/organizations/me", headers=SELLER)
    assert private.status_code == 200 and "contact_email" in private.json()


def test_complete_draft_patch_publish_pause(market_client):
    client = market_client
    result = client.post("/api/v1/lots", headers=SELLER, json=lot_payload() | {"status":"DRAFT", "resale_confirmed":False, "information_confirmed":False})
    assert result.status_code == 201, result.text
    key = result.json()["id"]
    assert client.get(f"/api/v1/lots/{key}").status_code == 404
    assert client.post(f"/api/v1/lots/{key}/publish", headers=SELLER).status_code == 422
    assert client.patch(f"/api/v1/lots/{key}", headers=BUYER, json={"quantity_total":500}).status_code == 403
    patch = client.patch(f"/api/v1/lots/{key}", headers=SELLER, json={"resale_confirmed":True, "information_confirmed":True})
    assert patch.status_code == 200, patch.text
    assert patch.json()["min_unit_price_minor"] == 11000
    published = client.post(f"/api/v1/lots/{key}/publish", headers=SELLER)
    assert published.status_code == 200 and published.json()["status"] == "ACTIVE"
    assert "min_unit_price_minor" not in client.get(f"/api/v1/lots/{key}").json()
    assert client.post(f"/api/v1/lots/{key}/pause", headers=SELLER).json()["status"] == "PAUSED"
    assert client.get(f"/api/v1/lots/{key}").status_code == 404


def test_public_inventory_excludes_expired_or_inactive_sellers(market_client, db):
    lot = db.get(SurplusLot, demo_id("lot-0"))
    lot.pickup_deadline = now() - timedelta(minutes=1)
    db.flush()
    assert market_client.get(f"/api/v1/lots/{lot.id}").status_code == 404
    assert str(lot.id) not in [item["id"] for item in market_client.get("/api/v1/lots").json()]
    lot.pickup_deadline = now() + timedelta(days=1)
    db.get(Organization, demo_id("org-0")).is_active = False
    db.flush()
    assert market_client.get(f"/api/v1/lots/{lot.id}").status_code == 404


def test_invalid_and_expired_inventory(market_client):
    for values in ({"quantity_total":0}, {"category":"unsupported"}, {"expiry_date":str(today() - timedelta(days=1))}):
        assert market_client.post("/api/v1/lots", headers=SELLER, json=lot_payload() | values).status_code == 422


def test_requirement_edit_ownership_and_pause(market_client):
    key = demo_id("requirement-0")
    assert market_client.patch(f"/api/v1/requirements/{key}", headers=SELLER, json={"required_quantity":10}).status_code == 403
    assert market_client.patch(f"/api/v1/requirements/{key}", headers=BUYER, json={"max_total_budget_minor":0}).status_code == 422
    assert market_client.patch(f"/api/v1/requirements/{key}", headers=BUYER, json={"required_quantity":0}).status_code == 422
    assert market_client.patch(f"/api/v1/requirements/{key}", headers=BUYER, json={"required_quantity":100}).json()["required_quantity"] == 100
    assert market_client.post(f"/api/v1/requirements/{key}/pause", headers=BUYER).json()["status"] == "PAUSED"


def test_demo_disabled_outside_development(app, market_client):
    app.state.settings.app_env = "production"
    assert market_client.get("/api/v1/organizations/me", headers=SELLER).status_code == 403
    assert market_client.post("/api/v1/lots", headers=SELLER, json=lot_payload()).status_code == 403
