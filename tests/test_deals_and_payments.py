from datetime import timedelta
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import select, func

from app.models import Deal, SurplusLot, Payment, DealEvent
from app.services.deal_service import expire_unpaid
from app.services.marketplace import now
from test_marketplace import SELLER, BUYER, make_deal


def test_full_collection_and_simulated_dashboard(market_client, db):
    client = market_client
    before = client.get("/api/v1/dashboard/summary", headers=SELLER).json()["platform_demo"]["total_simulated_platform_revenue_minor"]
    lot, _, deal = make_deal(client)
    key = deal["id"]
    assert client.get("/api/v1/deals", headers=BUYER).status_code == 200
    assert client.get(f"/api/v1/deals/{key}/payment", headers=BUYER).status_code == 404
    assert client.get(f"/api/v1/deals/{key}/pickup-details", headers=BUYER).status_code == 403
    assert client.post(f"/api/v1/deals/{key}/complete", headers=SELLER).status_code == 409
    checkout = client.post(f"/api/v1/deals/{key}/checkout", headers=BUYER)
    assert checkout.status_code == 200, checkout.text
    assert checkout.json()["status"] == "PENDING"
    payment = checkout.json()["payment_id"]
    assert client.post(f"/api/v1/payments/mock/{payment}/succeed", headers=SELLER).status_code == 403
    paid = client.post(f"/api/v1/payments/mock/{payment}/succeed", headers=BUYER)
    assert paid.json()["deal"]["status"] == "PAID"
    assert client.get(f"/api/v1/deals/{key}/pickup-details", headers=BUYER).json()["pickup_address"] == "PRIVATE LOCATION"
    assert client.post(f"/api/v1/deals/{key}/complete", headers=BUYER).status_code == 403
    assert client.post(f"/api/v1/deals/{key}/cancel", headers=SELLER).status_code == 409
    assert client.get("/api/v1/dashboard/summary", headers=SELLER).json()["platform_demo"]["total_simulated_platform_revenue_minor"] == before
    completed = client.post(f"/api/v1/deals/{key}/complete", headers=SELLER)
    assert completed.status_code == 200 and completed.json()["status"] == "COMPLETED"
    current = db.get(SurplusLot, UUID(lot["id"]))
    assert current.quantity_reserved == 0 and current.quantity_sold == 150 and current.available_quantity == 50
    assert client.post(f"/api/v1/deals/{key}/complete", headers=SELLER).status_code == 409
    assert client.post(f"/api/v1/deals/{key}/cancel", headers=BUYER).status_code == 409
    summary = client.get("/api/v1/dashboard/summary", headers=SELLER).json()
    assert summary["platform_demo"]["total_simulated_platform_revenue_minor"] == before + 72000
    assert summary["simulated"] is True
    assert client.get("/api/v1/dashboard/summary", headers=BUYER).json()["platform_demo"] is None
    assert client.get(f"/api/v1/deals/{key}/payment", headers=BUYER).json()["status"] == "SUCCEEDED"


def test_failed_attempt_retry_and_duplicate_events(market_client, db):
    client = market_client
    _, _, deal = make_deal(client)
    key = deal["id"]
    first = client.post(f"/api/v1/deals/{key}/checkout", headers=BUYER).json()["payment_id"]
    failed = client.post(f"/api/v1/payments/mock/{first}/fail", headers=BUYER)
    assert failed.json()["deal"]["status"] == "AWAITING_PAYMENT"
    assert client.post(f"/api/v1/payments/mock/{first}/fail", headers=BUYER).status_code == 200
    assert client.post(f"/api/v1/payments/mock/{first}/succeed", headers=BUYER).status_code == 409
    second = client.post(f"/api/v1/deals/{key}/checkout", headers=BUYER).json()["payment_id"]
    assert second != first
    assert client.get(f"/api/v1/deals/{key}/payment", headers=BUYER).json()["id"] == second
    assert client.post(f"/api/v1/payments/mock/{second}/succeed", headers=BUYER).status_code == 200
    assert client.post(f"/api/v1/payments/mock/{second}/succeed", headers=BUYER).status_code == 200
    assert client.post(f"/api/v1/payments/mock/{second}/fail", headers=BUYER).status_code == 409
    count = db.scalar(select(func.count()).select_from(DealEvent).where(DealEvent.deal_id == UUID(key), DealEvent.event_type == "MOCK_PAYMENT_SUCCEEDED"))
    assert count == 1


def test_unpaid_cancellation_releases_stock_and_prevents_payment(market_client, db):
    client = market_client
    lot, _, deal = make_deal(client)
    payment = client.post(f"/api/v1/deals/{deal['id']}/checkout", headers=BUYER).json()["payment_id"]
    cancelled = client.post(f"/api/v1/deals/{deal['id']}/cancel", headers=BUYER)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert db.get(SurplusLot, UUID(lot["id"])).quantity_reserved == 0
    assert db.get(Payment, UUID(payment)).status == "FAILED"
    assert client.post(f"/api/v1/deals/{deal['id']}/checkout", headers=BUYER).status_code == 409
    assert client.post(f"/api/v1/payments/mock/{payment}/succeed", headers=BUYER).status_code == 409


def test_explicit_unpaid_expiration(market_client, db):
    lot, _, deal = make_deal(market_client)
    with patch("app.services.deal_service.now", return_value=now() + timedelta(hours=2)):
        assert expire_unpaid(db) >= 1
    assert db.get(Deal, UUID(deal["id"])).status == "CANCELLED"
    assert db.get(SurplusLot, UUID(lot["id"])).quantity_reserved == 0


def test_callback_disabled_in_production(app, market_client):
    _, _, deal = make_deal(market_client)
    payment = market_client.post(f"/api/v1/deals/{deal['id']}/checkout", headers=BUYER).json()["payment_id"]
    app.state.settings.app_env = "production"
    assert market_client.post(f"/api/v1/payments/mock/{payment}/succeed", headers=BUYER).status_code == 403
