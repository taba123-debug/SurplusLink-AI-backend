import json
import logging
import re
from datetime import timedelta

from fastapi import HTTPException, Request
from pydantic import ValidationError

from app.schemas.extraction import LotExtraction, RequirementExtraction
from app.schemas.marketplace import LotCreate, RequirementCreate
from app.services.marketplace import today
from app.services.ai_provider import AIProvider
from app.services.ai_prompts import PROMPTS, COMMON

logger = logging.getLogger(__name__)


class HostedProvider:
    def __init__(self, settings):
        self.settings = settings

    def complete(self, kind, text, schema, reference_date=None, timezone=None):
        from openai import OpenAI, APIError, APITimeoutError
        settings = self.settings
        if settings.ai_provider != "groq" or not settings.groq_api_key or not settings.groq_api_key.get_secret_value().strip():
            raise HTTPException(503, "Hosted AI is not configured. Set GROQ_API_KEY; no mock fallback is enabled.")
        reference = f" Supplied reference date: {reference_date}; timezone: {timezone}. " if reference_date and timezone else " No date/timezone reference supplied. "
        system = PROMPTS[kind] + COMMON + reference + "Schema: " + json.dumps(schema.model_json_schema())
        try:
            with OpenAI(api_key=settings.groq_api_key.get_secret_value(), base_url=settings.ai_base_url,
                        timeout=settings.ai_timeout_seconds, max_retries=0) as client:
                result = client.chat.completions.create(model=settings.ai_model, temperature=0,
                    max_tokens=1200, response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": text}])
            if not result.choices or result.choices[0].finish_reason != "stop":
                raise HTTPException(502, "AI returned incomplete output. Review manually or retry.")
            return result.choices[0].message.content or ""
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            logger.warning("event=ai_provider_failed exception_type=%s provider_status=%s", type(exc).__name__, status)
            if isinstance(exc, APITimeoutError):
                raise HTTPException(504, "Hosted AI timed out. You can enter structured data manually.") from None
            if status in (401, 402, 403, 404, 429):
                raise HTTPException(503, "Hosted AI access, model or quota is unavailable. You can enter structured data manually.") from None
            raise HTTPException(502, "Hosted AI request failed. You can enter structured data manually.") from None


class DeterministicMockProvider:
    """Explicit test-only fixtures, not a substitute for live inference."""
    def complete(self, kind, text, schema, reference_date=None, timezone=None):
        lot = "200 sealed biscuit packs in Gulberg, asking Rs. 140 per pack, minimum Rs. 110, expiry in 45 days."
        requirement = "Need 150 biscuit packs under Rs. 20,000 in Lahore, minimum 30 days remaining."
        if kind == "lot" and text == lot:
            return json.dumps(dict(category="biscuits", quantity_total=200, unit="pack", packaging_type="sealed",
                asking_unit_price_rupees="140", min_unit_price_rupees="110", pickup_area="Gulberg",
                expiry_date=str(today() + timedelta(days=45)), evidence={"category":"biscuit", "quantity_total":"200", "unit":"packs",
                    "packaging_type":"sealed", "asking_unit_price_rupees":"Rs. 140", "min_unit_price_rupees":"Rs. 110",
                    "pickup_area":"Gulberg", "expiry_date":"expiry in 45 days"}))
        if kind == "requirement" and text == requirement:
            return json.dumps(dict(category="biscuits", required_quantity=150, unit="pack", max_total_budget_rupees="20000",
                city="Lahore", min_shelf_life_days=30, evidence={"category":"biscuit", "required_quantity":"150", "unit":"packs",
                "max_total_budget_rupees":"Rs. 20,000", "city":"Lahore", "min_shelf_life_days":"30 days"}))
        return "{}"


def get_provider(request: Request):
    settings = request.app.state.settings
    if settings.ai_provider == "mock":
        from app.api.dependencies import require_demo
        require_demo(request)
        return DeterministicMockProvider()
    return HostedProvider(settings)


def parse(kind, text, provider: AIProvider, reference_date=None, timezone=None):
    schema = LotExtraction if kind == "lot" else RequirementExtraction
    raw = provider.complete(kind, text, schema, reference_date=reference_date, timezone=timezone)
    try:
        data = schema.model_validate_json(raw)
        # Discard unsupported fields rather than presenting invented facts.
        for name in schema.model_fields:
            if name == "evidence" or getattr(data, name) is None:
                continue
            evidence = data.evidence.get(name)
            if not evidence or evidence not in text:
                setattr(data, name, None)
        data.evidence = {k: v for k, v in data.evidence.items() if k in schema.model_fields and k != "evidence" and getattr(data, k) is not None and v in text}
        if kind == "lot":
            relative = re.search(r"(?:expir\w*\s+)?in\s+(\d+)\s+days?", text, flags=re.IGNORECASE)
            if relative:
                days = int(relative.group(1))
                if days > 3650:
                    raise ValueError("Expiry range exceeds supported horizon")
                data.relative_expiry_expression = relative.group(0)
                data.remaining_shelf_life_days = days
                data.expiry_date = reference_date + timedelta(days=days) if reference_date and timezone else None
            elif data.remaining_shelf_life_days is not None or data.relative_expiry_expression is not None:
                data.expiry_date = None
        if kind == "lot" and data.min_unit_price_minor and data.asking_unit_price_minor and data.min_unit_price_minor > data.asking_unit_price_minor:
            raise ValueError("Inconsistent prices")
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(502, "AI returned invalid structured data. Nothing was saved; review manually or retry.") from None
    target = LotCreate if kind == "lot" else RequirementCreate
    values = data.model_dump(mode="json")
    missing = [name for name, field in target.model_fields.items() if field.is_required() and values.get(name) is None]
    simulated = isinstance(provider, DeterministicMockProvider)
    return dict(provider="deterministic_mock" if simulated else "groq",
        model="test-fixtures" if simulated else provider.settings.ai_model, simulated=simulated, mode="mock" if simulated else "live",
        data=data, missing_fields=missing, needs_review=True, persisted=False)


GroqProvider = HostedProvider
MockAIProvider = DeterministicMockProvider


if __name__ == "__main__":
    from app.ai_smoke import main
    raise SystemExit(main())
