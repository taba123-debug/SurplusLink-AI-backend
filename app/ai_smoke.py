"""Opt-in real Groq extraction checks; never writes marketplace data."""
import json

from fastapi import HTTPException

from app.core.config import get_settings
from app.services.ai import HostedProvider, parse
from app.services.marketplace import today


def main():
    settings = get_settings()
    if settings.ai_provider != "groq":
        print("LIVE_SMOKE_NOT_RUN: AI_PROVIDER is not groq; mock results are not live inference.")
        return 0
    if not settings.groq_api_key or not settings.groq_api_key.get_secret_value().strip():
        print("LIVE_SMOKE_NOT_RUN: GROQ_API_KEY is not configured.")
        return 0
    cases = [
        ("lot", "200 sealed biscuit packs in Gulberg, asking Rs. 140 per pack, minimum Rs. 110, expiry in 45 days.",
         {"quantity_total":200, "category":"biscuits", "unit":"pack", "asking_unit_price_minor":14000, "min_unit_price_minor":11000, "city":None}),
        ("requirement", "Need 150 biscuit packs under Rs. 20,000 in Lahore, minimum 30 days remaining.",
         {"required_quantity":150, "category":"biscuits", "unit":"pack", "max_total_budget_minor":2000000, "min_shelf_life_days":30}),
    ]
    for kind, description, expected in cases:
        try:
            result = parse(kind, description, HostedProvider(settings), today(), "Asia/Karachi")
            data = result["data"].model_dump(mode="json")
            mismatches = [key for key, value in expected.items() if data.get(key) != value]
            print(json.dumps({"case":kind, "provider":result["provider"], "model":result["model"],
                "mode":result["mode"], "simulated":result["simulated"], "data":data,
                "missing_fields":result["missing_fields"], "persisted":False,
                "expected_fields_passed":not mismatches, "mismatched_fields":mismatches}, indent=2))
            if mismatches:
                print(f"LIVE_SMOKE_FAILED: {kind} returned unexpected extraction values.")
                return 1
        except HTTPException as exc:
            print(f"LIVE_SMOKE_FAILED: {kind} HTTP {exc.status_code}: {exc.detail}")
            return 1
    print("LIVE_SMOKE_PASSED: both real GroqCloud extraction responses validated; no data persisted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
