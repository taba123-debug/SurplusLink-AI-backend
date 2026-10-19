from uuid import UUID

from fastapi import APIRouter

from app.api.v1.marketplace import DB, Org, Manager, Actor
from app.schemas.marketplace import CheckoutResponse, PaymentResponse
from app.services import payment_service

router = APIRouter(tags=["Demo payments"])


@router.get("/deals/{id}/payment", response_model=PaymentResponse)
def current_payment(id: UUID, session: DB, organization: Org):
    return payment_service.latest_payment(session, organization, id)


@router.post("/payments/mock/{id}/succeed", response_model=CheckoutResponse, summary="DEMO ONLY: simulate successful payment")
def succeed(id: UUID, session: DB, organization: Manager, actor: Actor):
    result = payment_service.resolve(session, organization, id, True, actor.user.id)
    return result | {"message":"DEMO ONLY: payment result simulated; no money moved."}


@router.post("/payments/mock/{id}/fail", response_model=CheckoutResponse, summary="DEMO ONLY: simulate failed payment")
def fail(id: UUID, session: DB, organization: Manager, actor: Actor):
    result = payment_service.resolve(session, organization, id, False, actor.user.id)
    return result | {"message":"DEMO ONLY: failed payment simulated; no money moved."}
