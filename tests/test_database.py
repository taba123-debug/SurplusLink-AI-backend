from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import Organization, OrganizationMembership, User, SurplusLot
from app.seed import demo_id, seed


def test_seed_relationships_and_idempotency(db):
    first = seed(db)
    second = seed(db)
    assert first == second
    assert db.scalar(select(func.count()).select_from(Organization)) == 5
    org = db.get(Organization, demo_id("org-0"))
    assert org.memberships[0].user.email == "user1@example.invalid"
    assert {demo_id("lot-0"), demo_id("lot-2")} <= {lot.id for lot in org.lots}


@pytest.mark.parametrize("sql", [
    "UPDATE surplus_lots SET quantity_total = 0",
    "UPDATE surplus_lots SET quantity_reserved = -1",
    "UPDATE surplus_lots SET quantity_sold = -1",
    "UPDATE surplus_lots SET quantity_reserved = quantity_total + 1",
    "UPDATE surplus_lots SET min_unit_price_minor = 0",
    "UPDATE surplus_lots SET asking_unit_price_minor = -1",
    "UPDATE surplus_lots SET seller_org_id = '00000000-0000-0000-0000-000000000000'",
    "UPDATE surplus_lots SET seller_org_id = NULL",
])
def test_database_constraints(db, sql):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text(sql))


def test_duplicate_email_and_membership(db):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(User(full_name="Duplicate", email="USER1@EXAMPLE.INVALID"))
        db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(OrganizationMembership(user_id=demo_id("user-0"), organization_id=demo_id("org-0"), role="OWNER"))
        db.flush()


def test_rollback(db):
    key = uuid4()
    transaction = db.begin_nested()
    db.add(User(id=key, full_name="Rollback", email=f"{key}@example.invalid"))
    db.flush()
    assert db.get(User, key)
    transaction.rollback()
    assert db.get(User, key) is None
