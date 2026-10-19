# GroqCloud migration and actual verification

The existing SDK adapter, extraction/Pydantic contracts, prompts and two parse endpoints are reused. GroqCloud replaces Hugging Face as the real provider. Explicit deterministic mock mode remains separate; real provider failures never return mocked results.

```env
AI_PROVIDER=groq
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=your_backend_secret
AI_TIMEOUT_SECONDS=20
```

The existing Compose `env_file: .env` passes all these values to the API. The running container was recreated and its provider/base URL/model plus key-presence flag were checked; no key was displayed. Existing database/password values were preserved. No dependency changes were needed: the installed OpenAI-compatible Python SDK sends JSON object response mode. See [Groq compatibility](https://console.groq.com/docs/openai) and [requested model capabilities](https://console.groq.com/docs/model/llama-3.1-8b-instant).

## Actual test results

- Focused AI tests after container recreation: **25 passed**.
- Full regression suite: **80 passed, 1 pre-existing TestClient/HTTPX deprecation warning**, none skipped.
- Groq model-list request with the configured key: **succeeded**.
- Requested `llama-3.1-8b-instant` present in the account's returned model list: **false**.
- Real inference request: **HTTP 404**, code `model_not_found`, message: “The model `llama-3.1-8b-instant` does not exist or you do not have access to it.”
- Live extraction smoke test: **failed**, client-safe HTTP 503 for unavailable hosted access/model. No extraction success is claimed.

Available model IDs returned included `qwen/qwen3.8-27b`, `openai/gpt-oss-20b`, and `openai/gpt-oss-120b`. These are account-list observations, not successful extraction tests. The requested model remains configured pending the user's choice; the implementation does not silently substitute another model.

An initial focused test run still used the old container's `AI_PROVIDER=huggingface` environment and failed settings validation. Rebuilding/recreating the API loaded Groq settings, after which all tests above passed. The model-access 404 remains a genuine external blocker.

## Next steps

Choose an accessible model explicitly or obtain access to the requested Llama model. After changing `.env`:

```powershell
docker compose up -d --build api
docker compose exec api python -m app.ai_smoke
```

The opt-in smoke command sends one lot and one requirement extraction to real GroqCloud, validates key expected fields, checks missing data stays null, labels the provider, and never persists marketplace records. It returns a nonzero exit code on provider or extraction failure. If no key exists, it reports NOT RUN. The older `python -m app.services.ai` command delegates to the same smoke test.

Database models, migrations, deterministic matching, offer/deal/payment services and marketplace behavior were not changed. The only adjacent runtime changes are AI key-presence metadata and AI provider labels in the existing demo. API schemas and both parse endpoints remain compatible.
