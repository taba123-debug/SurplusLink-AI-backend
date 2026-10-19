"""Explicit idempotent fictional demo data: python -m app.seed."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.db.session import create_session_factory
from app.models import Organization, User, OrganizationMembership, SurplusLot, BuyerRequirement


def demo_id(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, "surpluslink-fictional-demo/" + name)


def seed(session) -> dict:
    now = datetime.now(timezone.utc)
    def add(model, seed_key, **values):
        session.execute(insert(model).values(id=demo_id(seed_key), **values).on_conflict_do_nothing(index_elements=["id"]))
    for i in range(5):
        seller = i < 2
        business_name = {0:"Gulberg Packaged Foods (fictional demo)", 2:"Johar Town Mini Mart (fictional demo)"}.get(i, f"Fictional {'Bakery' if seller else 'Retail'} {i + 1}")
        add(Organization, f"org-{i}", name=business_name,
            business_type="BAKERY" if seller else "RETAILER", city="lahore", area="Gulberg",
            address="Fictional demo location, Lahore", contact_email=f"business{i + 1}@example.invalid")
        add(User, f"user-{i}", full_name=f"Demo User {i + 1}", email=f"user{i + 1}@example.invalid")
        add(OrganizationMembership, f"membership-{i}", organization_id=demo_id(f"org-{i}"), user_id=demo_id(f"user-{i}"), role="OWNER")
    # Upgrade only the two known original fictional placeholders; preserve any
    # developer-customized names and every inventory/payment record.
    from sqlalchemy import update
    for i, old_name, new_name in [(0,"Fictional Bakery 1","Gulberg Packaged Foods (fictional demo)"), (2,"Fictional Retail 3","Johar Town Mini Mart (fictional demo)")]:
        session.execute(update(Organization).where(Organization.id == demo_id(f"org-{i}"), Organization.name == old_name).values(name=new_name))
    for i in range(3):
        add(SurplusLot, f"lot-{i}", seller_org_id=demo_id(f"org-{i % 2}"), product_name=f"Sealed biscuit packs {i + 1}",
            category="biscuits", description="Fictional sealed bakery inventory for demo only.",
            quantity_total=200 + i * 50, unit="pack", asking_unit_price_minor=14000,
            min_unit_price_minor=11000, minimum_order_quantity=10, packaging_type="sealed",
            storage_type="ambient", manufacture_date=now.date() - timedelta(days=5),
            expiry_date=now.date() + timedelta(days=45 + i), city="lahore", pickup_area="Gulberg",
            pickup_address="Private fictional pickup location", pickup_deadline=now + timedelta(days=7),
            resale_confirmed=True, information_confirmed=True)
        add(BuyerRequirement, f"requirement-{i}", buyer_org_id=demo_id(f"org-{i + 2}"),
            title=f"Biscuit packs for fictional store {i + 1}", original_description="Need 150 biscuit packs in Lahore.",
            category="biscuits", required_quantity=150, unit="pack", max_total_budget_minor=2000000 + i * 500000,
            min_shelf_life_days=30, city="lahore", preferred_area="Gulberg")
    return {"seller_org_id": str(demo_id("org-0")), "seller_user_id":str(demo_id("user-0")),
            "buyer_org_id": str(demo_id("org-2")), "buyer_user_id":str(demo_id("user-2")),
            "lot_id": str(demo_id("lot-0")), "requirement_id": str(demo_id("requirement-0"))}


if __name__ == "__main__":
    import json
    engine, factory = create_session_factory(get_settings())
    with factory.begin() as session:
        result = seed(session)
    engine.dispose()
    print(json.dumps(result, indent=2))
