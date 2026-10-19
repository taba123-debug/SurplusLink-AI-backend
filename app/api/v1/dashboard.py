from fastapi import APIRouter, Request

from app.api.v1.marketplace import DB, Actor
from app.schemas.marketplace import DashboardResponse
from app.services.dashboard_service import summary

router = APIRouter(tags=["Demo dashboard"])


@router.get("/dashboard/summary", response_model=DashboardResponse)
def dashboard(session: DB, actor: Actor):
    return summary(session, actor)


@router.get("/demo/metadata")
def metadata(request: Request, actor: Actor):
    settings = request.app.state.settings
    return {"authentication":"development-only fictional membership selection", "user_id":actor.user.id,
        "organization_id":actor.organization.id, "role":actor.membership.role,
        "ai_mode":"mock" if settings.ai_provider == "mock" else "live",
        "ai_model":settings.ai_model, "hosted_token_configured":bool(settings.groq_api_key), "payments_simulated":True}
