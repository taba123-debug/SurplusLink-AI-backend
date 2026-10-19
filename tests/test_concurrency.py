from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import SurplusLot, Offer, Organization, Deal, Payment
from app.seed import demo_id
from app.services.marketplace import now, respond, checkout
from app.services.payment_service import resolve
from app.services.deal_service import cancel, complete


def setup_race(engine, quantity=150):
    with Session(engine) as session:
        source = session.get(SurplusLot, demo_id("lot-0"))
        values = {c.name: getattr(source, c.name) for c in SurplusLot.__table__.columns if c.name not in ("id", "created_at", "updated_at")}
        values.update(quantity_total=200, quantity_reserved=0, quantity_sold=0)
        lot = SurplusLot(**values)
        session.add(lot)
        session.flush()
        offers = [Offer(lot_id=lot.id, buyer_org_id=demo_id(f"org-{i + 2}"), quantity=quantity,
            offered_unit_price_minor=12000, expires_at=now() + timedelta(hours=1)) for i in range(2)]
        session.add_all(offers)
        session.commit()
        return lot.id, [offer.id for offer in offers]


def test_concurrent_acceptance_cannot_oversell(db_engine):
    lot_id, offers = setup_race(db_engine)
    barrier = Barrier(2)
    def accept(key):
        with Session(db_engine, expire_on_commit=False) as session:
            organization = session.get(Organization, demo_id("org-0"))
            barrier.wait(timeout=10)
            try:
                result = respond(session, organization, key, "ACCEPT")
                return result["deal"].id
            except HTTPException as exc:
                session.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, offers))
    assert results.count(409) == 1
    with Session(db_engine) as session:
        lot = session.get(SurplusLot, lot_id)
        assert lot.quantity_reserved == 150 and lot.available_quantity == 50
        assert session.scalar(select(func.count()).select_from(Deal).where(Deal.lot_id == lot_id)) == 1


def test_same_offer_acceptance_and_checkout_concurrently(db_engine):
    lot_id, offers = setup_race(db_engine, quantity=50)
    barrier = Barrier(2)
    def accept(_):
        with Session(db_engine, expire_on_commit=False) as session:
            organization = session.get(Organization, demo_id("org-0"))
            barrier.wait(timeout=10)
            return respond(session, organization, offers[0], "ACCEPT")["deal"].id
    with ThreadPoolExecutor(max_workers=2) as pool:
        deals = list(pool.map(accept, range(2)))
    assert deals[0] == deals[1]
    barrier = Barrier(2)
    def pay(_):
        with Session(db_engine, expire_on_commit=False) as session:
            organization = session.get(Organization, demo_id("org-2"))
            barrier.wait(timeout=10)
            return checkout(session, organization, deals[0])["payment"].id
    with ThreadPoolExecutor(max_workers=2) as pool:
        payments = list(pool.map(pay, range(2)))
    assert payments[0] == payments[1]
    barrier = Barrier(2)
    def succeed(_):
        with Session(db_engine, expire_on_commit=False) as session:
            organization = session.get(Organization, demo_id("org-2"))
            barrier.wait(timeout=10)
            return resolve(session, organization, payments[0], True)["payment"].id
    with ThreadPoolExecutor(max_workers=2) as pool:
        callbacks = list(pool.map(succeed, range(2)))
    assert callbacks[0] == callbacks[1]
    with Session(db_engine) as session:
        assert session.get(SurplusLot, lot_id).quantity_reserved == 50
        assert session.scalar(select(func.count()).select_from(Payment).where(Payment.deal_id == deals[0])) == 1


def accepted_payment(engine):
    lot_id, offers = setup_race(engine, quantity=50)
    with Session(engine, expire_on_commit=False) as session:
        seller = session.get(Organization, demo_id("org-0"))
        deal = respond(session, seller, offers[0], "ACCEPT")["deal"]
        buyer = session.get(Organization, demo_id("org-2"))
        payment = checkout(session, buyer, deal.id)["payment"]
        return lot_id, deal.id, payment.id


def test_cancel_and_success_race_are_mutually_exclusive(db_engine):
    lot_id, deal_id, payment_id = accepted_payment(db_engine)
    barrier = Barrier(2)
    def transition(success):
        with Session(db_engine, expire_on_commit=False) as session:
            buyer = session.get(Organization, demo_id("org-2"))
            barrier.wait(timeout=10)
            try:
                if success:
                    resolve(session, buyer, payment_id, True)
                else:
                    cancel(session, buyer, deal_id)
                return "success"
            except HTTPException as exc:
                session.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(transition, [False, True]))
    assert results.count("success") == 1 and results.count(409) == 1
    with Session(db_engine) as session:
        deal = session.get(Deal, deal_id)
        lot = session.get(SurplusLot, lot_id)
        assert lot.quantity_reserved == (50 if deal.status == "PAID" else 0)
        assert deal.status in ("PAID", "CANCELLED")


def test_concurrent_collection_moves_stock_once(db_engine):
    lot_id, deal_id, payment_id = accepted_payment(db_engine)
    with Session(db_engine, expire_on_commit=False) as session:
        buyer = session.get(Organization, demo_id("org-2"))
        resolve(session, buyer, payment_id, True)
    barrier = Barrier(2)
    def collect(_):
        with Session(db_engine, expire_on_commit=False) as session:
            seller = session.get(Organization, demo_id("org-0"))
            barrier.wait(timeout=10)
            try:
                complete(session, seller, deal_id)
                return "completed"
            except HTTPException as exc:
                session.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(collect, range(2)))
    assert results.count("completed") == 1 and results.count(409) == 1
    with Session(db_engine) as session:
        lot = session.get(SurplusLot, lot_id)
        assert lot.quantity_sold == 50 and lot.quantity_reserved == 0
