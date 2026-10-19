"""Repeatable local HTTP demo: docker compose exec api python -m app.demo."""
import json
import os
from datetime import timedelta

import httpx

from app.seed import demo_id
from app.services.marketplace import now, today


def run(live_ai=False, confirm_demo_data=False):
    seller = {"X-Demo-Org-ID": str(demo_id("org-0")), "X-Demo-User-ID": str(demo_id("user-0"))}
    buyer = {"X-Demo-Org-ID": str(demo_id("org-2")), "X-Demo-User-ID": str(demo_id("user-2"))}
    with httpx.Client(base_url=os.getenv("DEMO_API_URL", "http://127.0.0.1:8000"), timeout=20) as client:
        def request(method, path, **kwargs):
            response = client.request(method, "/api/v1" + path, **kwargs)
            response.raise_for_status()
            return response.json()
        ai_mode = "manual structured fixture; AI not invoked"
        lot_values, requirement_values = {}, {}
        if live_ai:
            if not confirm_demo_data:
                raise SystemExit("Use --live-ai --confirm-demo-data to confirm the known fictional scenario before persistence.")
            metadata = request("GET", "/demo/metadata", headers=seller)
            if metadata["ai_mode"] != "live" or not metadata["hosted_token_configured"]:
                raise SystemExit("Live GroqCloud mode and GROQ_API_KEY are required; no mock fallback.")
            lot_parse = request("POST", "/ai/parse-lot", headers=seller, json=dict(
                description="200 sealed biscuit packs in Gulberg, Lahore, asking Rs. 140 per pack, minimum Rs. 110, expiry in 45 days.",
                reference_date=str(today()), timezone="Asia/Karachi"))
            buyer_parse = request("POST", "/ai/parse-requirement", headers=buyer, json=dict(
                description="Need 150 biscuit packs under Rs. 20,000 in Lahore, minimum 30 days remaining."))
            assert lot_parse["mode"] == buyer_parse["mode"] == "live"
            assert lot_parse["data"]["quantity_total"] == 200 and lot_parse["data"]["asking_unit_price_minor"] == 14000
            assert lot_parse["data"]["min_unit_price_minor"] == 11000
            assert buyer_parse["data"]["required_quantity"] == 150 and buyer_parse["data"]["max_total_budget_minor"] == 2000000
            assert buyer_parse["data"]["min_shelf_life_days"] == 30
            lot_values = {key:lot_parse["data"][key] for key in ("category","quantity_total","unit","asking_unit_price_minor","min_unit_price_minor","expiry_date","city","pickup_area","packaging_type")}
            requirement_values = {key:buyer_parse["data"][key] for key in ("category","required_quantity","unit","max_total_budget_minor","min_shelf_life_days","city")}
            if any(value is None for value in (*lot_values.values(), *requirement_values.values())):
                raise SystemExit("AI omitted required demo values. Review manually; no records persisted.")
            ai_mode = "live hosted GroqCloud; both extraction requests succeeded"
        before = request("GET", "/dashboard/summary", headers=seller)["platform_demo"]["total_simulated_platform_revenue_minor"]
        body = dict(
            product_name="Demo sealed biscuit packs", category="biscuits", description="Fictional demo inventory.",
            quantity_total=200, unit="pack", asking_unit_price_minor=14000, min_unit_price_minor=11000,
            minimum_order_quantity=10, packaging_type="sealed", storage_type="ambient",
            expiry_date=str(today() + timedelta(days=45)), city="Lahore", pickup_area="Gulberg",
            pickup_address="Private fictional demo location", pickup_deadline=(now() + timedelta(days=3)).isoformat(),
            resale_confirmed=True, information_confirmed=True, status="DRAFT")
        body.update(lot_values)
        lot = request("POST", "/lots", headers=seller, json=body)
        request("POST", f"/lots/{lot['id']}/publish", headers=seller)
        requirement_body = dict(
            title="Demo biscuit purchase", original_description="Need 150 biscuit packs under Rs. 20,000 in Lahore, minimum 30 days remaining.",
            category="biscuits", required_quantity=150, unit="pack", max_total_budget_minor=2000000,
            min_shelf_life_days=30, city="lahore")
        requirement_body.update(requirement_values)
        requirement = request("POST", "/requirements", headers=buyer, json=requirement_body)
        matches = request("GET", f"/requirements/{requirement['id']}/matches", headers=buyer)
        reverse = request("GET", f"/lots/{lot['id']}/matching-buyers", headers=seller)
        offer = request("POST", f"/lots/{lot['id']}/offers", headers=buyer, json=dict(
            requirement_id=requirement["id"], quantity=150, offered_unit_price_minor=12000,
            expires_at=(now() + timedelta(hours=1)).isoformat()))
        accepted = request("POST", f"/offers/{offer['id']}/respond", headers=seller, json={"action":"ACCEPT"})
        deal = accepted["deal"]
        payment = request("POST", f"/deals/{deal['id']}/checkout", headers=buyer)
        assert payment["status"] == "PENDING"
        paid = request("POST", f"/payments/mock/{payment['payment_id']}/succeed", headers=buyer)
        assert paid["deal"]["status"] == "PAID"
        request("GET", f"/deals/{deal['id']}/pickup-details", headers=buyer)
        duplicate = request("POST", f"/deals/{deal['id']}/checkout", headers=buyer)
        assert payment["payment"]["id"] == duplicate["payment"]["id"]
        assert deal["buyer_total_minor"] == 1836000 and deal["seller_net_minor"] == 1764000
        assert any(item["lot"]["id"] == lot["id"] for item in matches)
        assert any(item["requirement"]["id"] == requirement["id"] for item in reverse)
        assert next(item for item in matches if item["lot_id"] == lot["id"])["match_type"] == "NEGOTIABLE"
        completed = request("POST", f"/deals/{deal['id']}/complete", headers=seller)
        inventory = request("GET", f"/lots/{lot['id']}")
        assert inventory["quantity_sold"] == 150 and inventory["available_quantity"] == 50 and inventory["quantity_reserved"] == 0
        after = request("GET", "/dashboard/summary", headers=seller)["platform_demo"]["total_simulated_platform_revenue_minor"]
        assert after - before == 72000
        print(json.dumps(dict(lot_id=lot["id"], requirement_id=requirement["id"], offer_id=offer["id"], deal_id=deal["id"],
            buyer_total_minor=deal["buyer_total_minor"], seller_net_minor=deal["seller_net_minor"],
            platform_gross_fee_minor=after - before, status=completed["status"], quantity_sold=inventory["quantity_sold"], available_quantity=inventory["available_quantity"],
            simulated=True, duplicate_checkout_reused_payment=True, ai=ai_mode), indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-ai", action="store_true")
    parser.add_argument("--confirm-demo-data", action="store_true")
    arguments = parser.parse_args()
    run(arguments.live_ai, arguments.confirm_demo_data)
