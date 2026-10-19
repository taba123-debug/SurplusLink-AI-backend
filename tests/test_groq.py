from unittest.mock import MagicMock, patch

from fastapi import HTTPException
import pytest

from app.core.config import Settings
from app.services.ai import HostedProvider, DeterministicMockProvider, parse


def test_groq_sdk_configuration_and_live_label():
    settings = Settings(_env_file=None, postgres_password="test", ai_provider="groq", groq_api_key="test-groq-secret")
    with patch("openai.OpenAI") as sdk:
        completion = sdk.return_value.__enter__.return_value.chat.completions.create
        completion.return_value = MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content="{}"))])
        result = parse("requirement", "Need stock", HostedProvider(settings))
        assert sdk.call_args.kwargs["api_key"] == "test-groq-secret"
        assert sdk.call_args.kwargs["base_url"] == "https://api.groq.com/openai/v1"
        assert completion.call_args.kwargs["model"] == "llama-3.1-8b-instant"
        assert completion.call_args.kwargs["response_format"] == {"type":"json_object"}
        assert result["provider"] == "groq" and result["mode"] == "live" and not result["simulated"]
        assert result["data"].required_quantity is None


@pytest.mark.parametrize("key", [None, "", "   "])
def test_no_groq_key_never_uses_sdk_or_mock(key):
    settings = Settings(_env_file=None, postgres_password="test", ai_provider="groq", groq_api_key=key)
    with patch("openai.OpenAI") as sdk, pytest.raises(HTTPException) as exc:
        parse("lot", "Some stock", HostedProvider(settings))
    assert exc.value.status_code == 503
    sdk.assert_not_called()


def test_live_smoke_does_not_call_provider_without_key():
    from app.ai_smoke import main
    settings = Settings(_env_file=None, postgres_password="test", ai_provider="groq", groq_api_key=None)
    with patch("app.ai_smoke.get_settings", return_value=settings), patch("app.ai_smoke.parse") as extraction:
        assert main() == 0
        extraction.assert_not_called()
