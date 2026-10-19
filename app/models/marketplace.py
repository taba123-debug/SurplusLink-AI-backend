from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Identity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Timestamps(Identity):
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Organization(Timestamps, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(150))
    business_type: Mapped[str] = mapped_column(String(30))
    verification_status: Mapped[str] = mapped_column(String(25), server_default="PENDING")
    city: Mapped[str] = mapped_column(String(100))
    area: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="organization")
    lots: Mapped[list["SurplusLot"]] = relationship(back_populates="seller")
    requirements: Mapped[list["BuyerRequirement"]] = relationship(back_populates="buyer")
    __table_args__ = (CheckConstraint("verification_status IN ('PENDING','VERIFIED','REJECTED')", name="verification_status"),)


class User(Timestamps, Base):
    __tablename__ = "users"
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="user")
    __table_args__ = (Index("uq_users_email_lower", func.lower(email), unique=True),)


class OrganizationMembership(Timestamps, Base):
    __tablename__ = "organization_memberships"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")
    __table_args__ = (UniqueConstraint("user_id", "organization_id"), CheckConstraint("role IN ('OWNER','MANAGER','STAFF')", name="role"))


class SurplusLot(Timestamps, Base):
    __tablename__ = "surplus_lots"
    seller_org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    product_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    original_description: Mapped[str | None] = mapped_column(Text)
    quantity_total: Mapped[int] = mapped_column(Integer)
    quantity_reserved: Mapped[int] = mapped_column(Integer, server_default="0")
    quantity_sold: Mapped[int] = mapped_column(Integer, server_default="0")
    unit: Mapped[str] = mapped_column(String(30))
    asking_unit_price_minor: Mapped[int] = mapped_column(BigInteger)
    min_unit_price_minor: Mapped[int] = mapped_column(BigInteger)
    minimum_order_quantity: Mapped[int] = mapped_column(Integer)
    packaging_type: Mapped[str] = mapped_column(String(50))
    storage_type: Mapped[str] = mapped_column(String(30))
    manufacture_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    city: Mapped[str] = mapped_column(String(100))
    pickup_area: Mapped[str] = mapped_column(String(120))
    pickup_address: Mapped[str] = mapped_column(Text)
    pickup_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resale_confirmed: Mapped[bool] = mapped_column(Boolean)
    information_confirmed: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20), server_default="ACTIVE")
    seller: Mapped[Organization] = relationship(back_populates="lots")
    offers: Mapped[list["Offer"]] = relationship(back_populates="lot")
    __table_args__ = (
        CheckConstraint("quantity_total > 0 AND quantity_reserved >= 0 AND quantity_sold >= 0 AND quantity_reserved + quantity_sold <= quantity_total", name="inventory"),
        CheckConstraint("asking_unit_price_minor > 0 AND min_unit_price_minor > 0 AND min_unit_price_minor <= asking_unit_price_minor", name="prices"),
        CheckConstraint("minimum_order_quantity > 0 AND minimum_order_quantity <= quantity_total", name="minimum_order"),
        CheckConstraint("manufacture_date IS NULL OR manufacture_date <= expiry_date", name="dates"),
        CheckConstraint("status IN ('DRAFT','ACTIVE','PAUSED','SOLD_OUT','CLOSED','EXPIRED')", name="status"),
        CheckConstraint("status <> 'ACTIVE' OR (resale_confirmed AND information_confirmed)", name="publication_confirmed"),
        Index("ix_lots_seller_status", "seller_org_id", "status"),
        Index("ix_lots_matching", "category", "unit", "city", "status", "expiry_date"),
    )

    @property
    def available_quantity(self) -> int:
        return self.quantity_total - self.quantity_reserved - self.quantity_sold


class BuyerRequirement(Timestamps, Base):
    __tablename__ = "buyer_requirements"
    buyer_org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    title: Mapped[str] = mapped_column(String(200))
    original_description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    required_quantity: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(30))
    max_total_budget_minor: Mapped[int] = mapped_column(BigInteger)
    min_shelf_life_days: Mapped[int] = mapped_column(Integer, server_default="0")
    city: Mapped[str] = mapped_column(String(100))
    preferred_area: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), server_default="ACTIVE")
    buyer: Mapped[Organization] = relationship(back_populates="requirements")
    __table_args__ = (
        UniqueConstraint("id", "buyer_org_id"),
        CheckConstraint("required_quantity > 0 AND max_total_budget_minor > 0 AND min_shelf_life_days >= 0", name="quantities_budget"),
        CheckConstraint("status IN ('ACTIVE','PAUSED','FULFILLED','CLOSED')", name="status"),
        Index("ix_requirements_buyer_status", "buyer_org_id", "status"),
        Index("ix_requirements_matching", "category", "unit", "city", "status"),
    )


class Offer(Timestamps, Base):
    __tablename__ = "offers"
    lot_id: Mapped[UUID] = mapped_column(ForeignKey("surplus_lots.id"), index=True)
    buyer_org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    requirement_id: Mapped[UUID | None]
    quantity: Mapped[int] = mapped_column(Integer)
    offered_unit_price_minor: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), server_default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lot: Mapped[SurplusLot] = relationship(back_populates="offers")
    deal: Mapped["Deal | None"] = relationship(back_populates="offer", foreign_keys="Deal.offer_id")
    __table_args__ = (
        ForeignKeyConstraint(["requirement_id", "buyer_org_id"], ["buyer_requirements.id", "buyer_requirements.buyer_org_id"], name="fk_offers_requirement_buyer"),
        CheckConstraint("quantity > 0 AND offered_unit_price_minor > 0", name="quantity_price"),
        CheckConstraint("status IN ('PENDING','ACCEPTED','REJECTED','WITHDRAWN','EXPIRED')", name="status"),
        UniqueConstraint("id", "lot_id", "buyer_org_id"),
        Index("ix_offers_status_expiry", "status", "expires_at"),
    )


class Deal(Timestamps, Base):
    __tablename__ = "deals"
    offer_id: Mapped[UUID] = mapped_column(ForeignKey("offers.id"), unique=True)
    lot_id: Mapped[UUID] = mapped_column(ForeignKey("surplus_lots.id"), index=True)
    buyer_org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    seller_org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    agreed_unit_price_minor: Mapped[int] = mapped_column(BigInteger)
    subtotal_minor: Mapped[int] = mapped_column(BigInteger)
    buyer_fee_bps: Mapped[int] = mapped_column(Integer, server_default="200")
    seller_fee_bps: Mapped[int] = mapped_column(Integer, server_default="200")
    buyer_fee_minor: Mapped[int] = mapped_column(BigInteger)
    seller_fee_minor: Mapped[int] = mapped_column(BigInteger)
    buyer_total_minor: Mapped[int] = mapped_column(BigInteger)
    seller_net_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), server_default="PKR")
    status: Mapped[str] = mapped_column(String(25), server_default="AWAITING_PAYMENT")
    offer: Mapped[Offer] = relationship(back_populates="deal", foreign_keys=[offer_id])
    payments: Mapped[list["Payment"]] = relationship(back_populates="deal")
    events: Mapped[list["DealEvent"]] = relationship(back_populates="deal")
    __table_args__ = (
        ForeignKeyConstraint(["offer_id", "lot_id", "buyer_org_id"], ["offers.id", "offers.lot_id", "offers.buyer_org_id"], name="fk_deals_offer_snapshot"),
        CheckConstraint("buyer_org_id <> seller_org_id", name="different_parties"),
        CheckConstraint("quantity > 0 AND agreed_unit_price_minor > 0 AND subtotal_minor = quantity::bigint * agreed_unit_price_minor", name="subtotal"),
        CheckConstraint("buyer_fee_bps BETWEEN 0 AND 10000 AND seller_fee_bps BETWEEN 0 AND 10000", name="fee_rates"),
        CheckConstraint("buyer_fee_minor = (subtotal_minor * buyer_fee_bps + 5000) / 10000 AND seller_fee_minor = (subtotal_minor * seller_fee_bps + 5000) / 10000", name="fee_rounding"),
        CheckConstraint("buyer_total_minor = subtotal_minor + buyer_fee_minor AND seller_net_minor = subtotal_minor - seller_fee_minor", name="totals"),
        CheckConstraint("currency = 'PKR'", name="currency"),
        CheckConstraint("status IN ('AWAITING_PAYMENT','PAID','COMPLETED','CANCELLED')", name="status"),
    )


class Payment(Timestamps, Base):
    __tablename__ = "payments"
    deal_id: Mapped[UUID] = mapped_column(ForeignKey("deals.id"), index=True)
    provider: Mapped[str] = mapped_column(String(30), server_default="MOCK")
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), server_default="PKR")
    status: Mapped[str] = mapped_column(String(20), server_default="PENDING")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deal: Mapped[Deal] = relationship(back_populates="payments")
    __table_args__ = (
        CheckConstraint("amount_minor > 0 AND currency = 'PKR' AND provider = 'MOCK'", name="amount_provider"),
        CheckConstraint("status IN ('PENDING','SUCCEEDED','FAILED')", name="status"),
        CheckConstraint("status <> 'SUCCEEDED' OR paid_at IS NOT NULL", name="paid_timestamp"),
        Index("uq_payments_success_per_deal", "deal_id", unique=True, postgresql_where=text("status = 'SUCCEEDED'")),
    )


class DealEvent(Identity, Base):
    __tablename__ = "deal_events"
    deal_id: Mapped[UUID] = mapped_column(ForeignKey("deals.id"), index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(60))
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    deal: Mapped[Deal] = relationship(back_populates="events")
