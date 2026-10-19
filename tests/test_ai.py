import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.schemas.extraction import LotExtraction
from app.services.ai import DeterministicMockProvider, HostedProvider, get_provider, parse

LOT = "200 sealed biscuit packs in Gulberg, asking Rs. 140 per pack, minimum Rs. 110, expiry in 45 days."
REQUIREMENT = "Need 150 biscuit packs under Rs. 20,000 in Lahore, minimum 30 days remaining."


def test_extraction_routes_no_persistence(app, client):
    from app.api.dependencies import get_identity
    app.dependency_overrides[get_identity] = lambda: object()
    app.dependency_overrides[get_provider] = lambda: DeterministicMockProvider()
    result = client.post("/api/v1/ai/parse-lot", json={"text": LOT})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["simulated"] and data["needs_review"] and not data["persisted"]
    assert data["data"]["asking_unit_price_minor"] == 14000
    assert data["data"]["min_unit_price_minor"] == 11000
    assert data["data"]["quantity_total"] == 200
    assert data["data"]["city"] is None
    assert "resale_confirmed" in data["missing_fields"]
    result = client.post("/api/v1/ai/parse-requirement", json={"text": REQUIREMENT})
    assert result.status_code == 200
    assert result.json()["data"]["max_total_budget_minor"] == 2000000
    assert result.json()["data"]["city"] == "lahore"


@pytest.mark.parametrize("raw", ['not json', '{"quantity_total":-1}', '{"asking_unit_price_rupees":"NaN"}', '{"asking_unit_price_rupees":"1.001"}', '{"resale_confirmed":true}'])
def test_invalid_ai_output_is_rejected(raw):
    provider = MagicMock()
    provider.complete.return_value = raw
    with pytest.raises(HTTPException) as error:
        parse("lot", LOT, provider)
    assert error.value.status_code == 502


def test_unsupported_values_are_null():
    provider = MagicMock()
    provider.complete.return_value = json.dumps({"expiry_date":"2099-01-01", "city":"Lahore", "evidence":{"city":"not in the input"}})
    result = parse("lot", "Some stock", provider)
    assert result["data"].expiry_date is None and result["data"].city is None
    assert result["data"].evidence == {}


def test_missing_token_never_falls_back():
    provider = HostedProvider(Settings(_env_file=None, postgres_password="test", groq_api_key=None))
    with pytest.raises(HTTPException) as error:
        provider.complete("lot", LOT, LotExtraction)
    assert error.value.status_code == 503


def test_provider_timeout_is_safe():
    from openai import APITimeoutError
    provider = HostedProvider(Settings(_env_file=None, postgres_password="test", groq_api_key="test-token"))
    with patch("openai.OpenAI") as sdk:
        sdk.return_value.__enter__.return_value.chat.completions.create.side_effect = APITimeoutError(request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))
        with pytest.raises(HTTPException) as error:
            provider.complete("lot", LOT, LotExtraction)
    assert error.value.status_code == 504
    assert "test-token" not in error.value.detail


def test_sdk_json_contract():
    provider = HostedProvider(Settings(_env_file=None, postgres_password="test", groq_api_key="test-token"))
    with patch("openai.OpenAI") as sdk:
        completion = sdk.return_value.__enter__.return_value.chat.completions.create
        completion.return_value = MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content="{}"))])
        assert provider.complete("lot", LOT, LotExtraction) == "{}"
        assert sdk.call_args.kwargs["base_url"] == "https://api.groq.com/openai/v1"
        assert sdk.call_args.kwargs["max_retries"] == 0
        assert completion.call_args.kwargs["response_format"] == {"type":"json_object"}
