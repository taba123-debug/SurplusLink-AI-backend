# React / TypeScript integration

API base: `http://localhost:8000/api/v1`. Development CORS: `http://localhost:5173`. Use [openapi.json](openapi.json) to generate/check DTOs. The separate frontend source was not available in this checkout, so no unverified DTO compatibility is claimed.

## Identity and HTTP client

Fetch `GET /demo/identities`, render the fictional choices, then retain the chosen user/organization UUID pair in local demo state. Send both `X-Demo-User-ID` and `X-Demo-Org-ID` for all private/mutation calls, AI and both matching directions. Identity selection is development-only and active membership/role is rechecked server-side. Do not send organization ownership fields in JSON bodies. Do not store GROQ_API_KEY or any provider credential in frontend code.

```typescript
const API = 'http://localhost:8000/api/v1';
type DemoIdentity = { user_id: string; organization_id: string };

export async function api<T>(path: string, identity?: DemoIdentity, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set('Content-Type', 'application/json');
  if (identity) {
    headers.set('X-Demo-User-ID', identity.user_id);
    headers.set('X-Demo-Org-ID', identity.organization_id);
  }
  const response = await fetch(`${API}${path}`, { ...init, headers });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message ?? 'Request failed');
  return body as T;
}
```

This is not production authentication. OWNER/MANAGER can write; STAFF is read-only. UI role gating is for usability; the server remains authoritative. Missing identity is 422, invalid membership/role 403, missing resources 404, conflicting states/stock 409, invalid data 422, AI provider/configuration errors 502/503/504. Errors use `{error:{code,message,details?}}`; validation details identify location/type without echoing secrets.

## Contracts and state flow

- Public lists are arrays with `limit` and `offset`, not invented pagination envelopes. Only ACTIVE eligible lots appear publicly; `/lots/mine` returns owned drafts/private fields. Public lot detail returns 404 for paused/expired/ineligible inventory.
- Lot quantity uses `quantity_total`; requirement quantity uses `required_quantity`. Money fields use integer paisa, not rupees. Display rupees by dividing by 100, but submit integer minor units. Dates are YYYY-MM-DD; pickup/offer timestamps require an offset.
- Allowed categories: biscuits/bread/cakes/pastries/rusks/buns; units: pack/carton/tray/piece. DTOs normalize common case/plural aliases. Category/unit/city matching is exact after normalization.
- Creation defaults to ACTIVE for backward compatibility; send `status:'DRAFT'` for the publish workflow. Drafts still require every non-null database field; flags may be false. Update with PATCH, then POST publish. Reserved/sold lots cannot be edited.
- Parsing accepts `{description, reference_date?, timezone?}` (legacy `text` alias supported). Use both reference fields together for relative dates. Outputs remain nested under `data`; prices are `*_minor`, seller quantity is `quantity_total`, unknowns null. `missing_fields`, `needs_review`, `mode`, `simulated`, and `persisted:false` are top-level. Always show a review form; require manual resale/information confirmation before a separate save request.
- `GET /demo/metadata` shows configured live/mock mode and token presence without exposing credentials. A hosted request can still fail despite token presence. Use manual structured forms on provider failure; never relabel mock results as real AI.
- Buyer matching is owner-scoped at `/requirements/{id}/matches`; reverse matching requires the lot seller. Match objects include a safe nested summary, ID, score, reasons and estimated subtotal/buyer fee/total. Scores: DIRECT 100, NEGOTIABLE 80. Hard-filter failures are absent. No hidden reserve-price hints are included.
- Offers may omit `expires_at`, defaulting to min(now + 24h, pickup deadline). A pending offer reserves nothing. ACCEPT/REJECT use POST respond; buyers can POST withdraw while pending. Acceptance below the confidential reserve is rejected with a generic seller-policy conflict. Never calculate final fees client-side.
- Checkout now creates/reuses a **PENDING** payment. This intentionally replaces the earlier one-step automatic-success behavior. Response includes `payment_id`, `deal_id`, `amount_minor`, `currency`, `status`, `simulated:true` plus nested `payment` and `deal`. No card entry is needed.
- Show explicit demo-only success/failure controls calling `/payments/mock/{payment_id}/succeed` or `/fail`. Success changes the deal to PAID; failure leaves it AWAITING_PAYMENT and allows a new attempt. Duplicate same-result callbacks reuse the result; a conflicting terminal result returns 409.
- Fetch `/deals/{id}/payment` for current payment state. After PAID, parties may GET pickup-details. Only the seller OWNER/MANAGER can POST complete to confirm physical collection. COMPLETED moves reserved inventory to sold; a payment alone never does.
- Cancel is allowed only while unpaid; it releases stock and fails pending attempts. Paid cancellation requires a refund flow, deliberately not implemented. Payment is due one hour after acceptance/creation and before product/collection expiry; the explicit cleanup CLI releases overdue unpaid reservations.
- `/dashboard/summary` returns buyer and seller aggregates for the current organization, all labelled simulated. `platform_demo` is null except for the designated first seeded seller OWNER. Revenue includes only completed deals with successful MOCK payments.

## Curl examples

Get IDs first; use returned values in these placeholders. Git Bash shell examples:

```bash
curl http://localhost:8000/api/v1/demo/identities
curl http://localhost:8000/api/v1/lots
curl -H "X-Demo-User-ID: $USER_ID" -H "X-Demo-Org-ID: $ORG_ID" \
  http://localhost:8000/api/v1/organizations/me
curl -H "X-Demo-User-ID: $BUYER_USER_ID" -H "X-Demo-Org-ID: $BUYER_ORG_ID" \
  http://localhost:8000/api/v1/requirements/$REQUIREMENT_ID/matches
curl -X POST -H 'Content-Type: application/json' \
  -H "X-Demo-User-ID: $SELLER_USER_ID" -H "X-Demo-Org-ID: $SELLER_ORG_ID" \
  -d '{"action":"ACCEPT"}' http://localhost:8000/api/v1/offers/$OFFER_ID/respond
curl -X POST -H "X-Demo-User-ID: $BUYER_USER_ID" -H "X-Demo-Org-ID: $BUYER_ORG_ID" \
  http://localhost:8000/api/v1/deals/$DEAL_ID/checkout
curl -X POST -H "X-Demo-User-ID: $BUYER_USER_ID" -H "X-Demo-Org-ID: $BUYER_ORG_ID" \
  http://localhost:8000/api/v1/payments/mock/$PAYMENT_ID/succeed
curl -X POST -H "X-Demo-User-ID: $SELLER_USER_ID" -H "X-Demo-Org-ID: $SELLER_ORG_ID" \
  http://localhost:8000/api/v1/deals/$DEAL_ID/complete
```

On PowerShell use `curl.exe`; Swagger's Try it out renders full request examples and identity headers. For a ready-to-run end-to-end scenario with relative dates and fresh records, use `docker compose exec api python -m app.demo`.

Regenerate OpenAPI after backend changes (PowerShell):

```powershell
docker compose exec -T api python -c "import json; from app.main import create_app; print(json.dumps(create_app().openapi(),indent=2))" | Set-Content -Encoding utf8 docs/openapi.json
```
