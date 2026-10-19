from sqlalchemy import select, func, or_

from app.models import BuyerRequirement, SurplusLot, Offer, Deal, Payment
from app.seed import demo_id
from app.services import catalog, marketplace


def summary(session, identity):
    org = identity.organization
    requirements = session.scalars(select(BuyerRequirement).where(BuyerRequirement.buyer_org_id == org.id, BuyerRequirement.status == "ACTIVE")).all()
    opportunities = {item["lot_id"] for requirement in requirements for item in marketplace.requirement_matches(session, requirement.id)}
    lots = session.scalars(catalog.eligible_lots_query().where(SurplusLot.seller_org_id == org.id)).all()
    def count(model, *conditions):
        return session.scalar(select(func.count()).select_from(model).where(*conditions))
    def aggregate(*conditions):
        # A completed deal contributes to simulated revenue only if its MOCK
        # payment actually succeeded. EXISTS avoids counting payment retries twice.
        paid = select(Payment.id).where(Payment.deal_id == Deal.id, Payment.provider == "MOCK", Payment.status == "SUCCEEDED").exists()
        result = session.execute(select(func.count(Deal.id), *[func.coalesce(func.sum(column), 0) for column in (
            Deal.subtotal_minor, Deal.buyer_fee_minor, Deal.seller_fee_minor, Deal.buyer_total_minor, Deal.seller_net_minor)])
            .where(Deal.status == "COMPLETED", paid, *conditions)).one()
        return tuple(int(value) for value in result)
    purchases = aggregate(Deal.buyer_org_id == org.id)
    sales = aggregate(Deal.seller_org_id == org.id)
    pending = (Offer.status == "PENDING", Offer.expires_at > marketplace.now())
    buyer = dict(active_requirements=len(requirements), compatible_opportunities_count=len(opportunities),
        pending_offers=count(Offer, Offer.buyer_org_id == org.id, *pending),
        accepted_deals=count(Deal, Deal.buyer_org_id == org.id, Deal.status != "CANCELLED"),
        completed_purchases=purchases[0], total_simulated_purchase_value_minor=purchases[4])
    incoming = session.scalar(select(func.count(Offer.id)).join(SurplusLot).where(SurplusLot.seller_org_id == org.id, *pending))
    reserved = session.scalar(select(func.coalesce(func.sum(SurplusLot.quantity_reserved), 0)).where(SurplusLot.seller_org_id == org.id))
    seller = dict(active_inventory_lots=len(lots), available_units=sum(item.available_quantity for item in lots),
        reserved_units=reserved, incoming_offers=incoming,
        accepted_deals=count(Deal, Deal.seller_org_id == org.id, Deal.status != "CANCELLED"),
        completed_wholesale_value_minor=sales[1], seller_fees_minor=sales[3], net_simulated_proceeds_minor=sales[5])
    platform = None
    # Explicit fictional platform-demo administrator; other organizations receive
    # their own metrics only. This is not a production administrator role.
    if identity.user.id == demo_id("user-0") and identity.membership.role == "OWNER" and org.id == demo_id("org-0"):
        totals = aggregate()
        platform = dict(completed_simulated_deals=totals[0], gross_completed_deal_value_minor=totals[1],
            total_simulated_buyer_fees_minor=totals[2], total_simulated_seller_fees_minor=totals[3],
            total_simulated_platform_revenue_minor=totals[2] + totals[3])
    return dict(organization_id=org.id, buyer=buyer, seller=seller, platform_demo=platform, simulated=True)
