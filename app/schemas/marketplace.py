from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

Quantity = Annotated[int, Field(gt=0, le=1000000)]
Money = Annotated[int, Field(gt=0, le=1000000000)]
Category = Literal["biscuits", "bread", "cakes", "pastries", "rusks", "buns"]
Unit = Literal["pack", "carton", "tray", "piece"]


def normalize(value: str) -> str:
    value = value.strip().lower().replace(" ", "_")
    return {"biscuit": "biscuits", "packs": "pack", "packets": "pack", "packet": "pack", "cartons": "carton", "trays": "tray", "pieces": "piece"}.get(value, value)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def nonempty_strings(cls, value):
        if isinstance(value, str) and not value:
            raise ValueError("Must not be empty")
        return value


class LotCreate(Input):
    product_name: str = Field(min_length=1, max_length=200)
    category: Category
    description: str = Field(min_length=1, max_length=10000)
    original_description: str | None = Field(default=None, max_length=10000)
    quantity_total: Quantity
    unit: Unit
    asking_unit_price_minor: Money
    min_unit_price_minor: Money
    minimum_order_quantity: Quantity
    packaging_type: Literal["sealed"]
    storage_type: Literal["ambient", "chilled", "frozen"]
    manufacture_date: date | None = None
    expiry_date: date
    city: str = Field(min_length=1, max_length=100)
    pickup_area: str = Field(min_length=1, max_length=120)
    pickup_address: str = Field(min_length=1, max_length=2000)
    pickup_deadline: AwareDatetime
    resale_confirmed: bool
    information_confirmed: bool
    status: Literal["DRAFT", "ACTIVE"] = "ACTIVE"

    @field_validator("category", "unit", "city", mode="before")
    @classmethod
    def normalize_fields(cls, value):
        return normalize(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def valid_lot(self):
        if self.status == "ACTIVE" and not (self.resale_confirmed and self.information_confirmed):
            raise ValueError("Publication requires resale and information confirmation")
        if self.min_unit_price_minor > self.asking_unit_price_minor:
            raise ValueError("Reserve must not exceed asking price")
        if self.minimum_order_quantity > self.quantity_total:
            raise ValueError("Minimum order exceeds total")
        if self.manufacture_date and self.manufacture_date > self.expiry_date:
            raise ValueError("Manufacture date exceeds expiry")
        return self


class RequirementCreate(Input):
    title: str = Field(min_length=1, max_length=200)
    original_description: str = Field(min_length=1, max_length=10000)
    category: Category
    required_quantity: Quantity
    unit: Unit
    max_total_budget_minor: Money
    min_shelf_life_days: int = Field(default=0, ge=0, le=3650)
    city: str = Field(min_length=1, max_length=100)
    preferred_area: str | None = Field(default=None, max_length=120)

    @field_validator("category", "unit", "city", mode="before")
    @classmethod
    def normalize_fields(cls, value):
        return normalize(value) if isinstance(value, str) else value


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LotPublic(Output):
    id: UUID
    seller_org_id: UUID
    product_name: str
    category: str
    description: str
    quantity_total: int
    quantity_reserved: int
    quantity_sold: int
    available_quantity: int
    unit: str
    asking_unit_price_minor: int
    minimum_order_quantity: int
    packaging_type: str
    storage_type: str
    manufacture_date: date | None
    expiry_date: date
    city: str
    pickup_area: str
    pickup_deadline: datetime
    resale_confirmed: bool
    information_confirmed: bool
    status: str
    created_at: datetime


class RequirementPublic(Output):
    id: UUID
    buyer_org_id: UUID
    title: str
    category: str
    required_quantity: int
    unit: str
    max_total_budget_minor: int
    min_shelf_life_days: int
    city: str
    preferred_area: str | None
    status: str
    created_at: datetime


class OfferCreate(Input):
    requirement_id: UUID | None = None
    quantity: Quantity
    offered_unit_price_minor: Money
    expires_at: AwareDatetime | None = None


class OfferResponse(Output):
    id: UUID
    lot_id: UUID
    buyer_org_id: UUID
    requirement_id: UUID | None
    quantity: int
    offered_unit_price_minor: int
    expires_at: datetime
    status: str
    created_at: datetime


class Respond(Input):
    action: Literal["ACCEPT", "REJECT"]


class DealResponse(Output):
    id: UUID
    offer_id: UUID
    lot_id: UUID
    buyer_org_id: UUID
    seller_org_id: UUID
    quantity: int
    agreed_unit_price_minor: int
    subtotal_minor: int
    buyer_fee_bps: int
    seller_fee_bps: int
    buyer_fee_minor: int
    seller_fee_minor: int
    buyer_total_minor: int
    seller_net_minor: int
    currency: str
    status: str
    created_at: datetime

    @computed_field
    @property
    def payment_due_at(self) -> datetime:
        from datetime import timedelta
        return self.created_at + timedelta(hours=1)


class RespondResponse(BaseModel):
    offer: OfferResponse
    deal: DealResponse | None


class PaymentResponse(Output):
    id: UUID
    deal_id: UUID
    provider: Literal["MOCK"]
    status: str
    amount_minor: int
    currency: str
    paid_at: datetime | None
    simulated: Literal[True] = True


class CheckoutResponse(BaseModel):
    simulated: Literal[True] = True
    message: str = "DEMO ONLY: pending mock payment; no money moved."
    payment: PaymentResponse
    deal: DealResponse

    @computed_field
    @property
    def payment_id(self) -> UUID:
        return self.payment.id

    @computed_field
    @property
    def deal_id(self) -> UUID:
        return self.deal.id

    @computed_field
    @property
    def amount_minor(self) -> int:
        return self.payment.amount_minor

    @computed_field
    @property
    def currency(self) -> str:
        return self.payment.currency

    @computed_field
    @property
    def status(self) -> str:
        return self.payment.status


class BuyerMetrics(BaseModel):
    active_requirements: int
    compatible_opportunities_count: int
    pending_offers: int
    accepted_deals: int
    completed_purchases: int
    total_simulated_purchase_value_minor: int


class SellerMetrics(BaseModel):
    active_inventory_lots: int
    available_units: int
    reserved_units: int
    incoming_offers: int
    accepted_deals: int
    completed_wholesale_value_minor: int
    seller_fees_minor: int
    net_simulated_proceeds_minor: int


class PlatformMetrics(BaseModel):
    completed_simulated_deals: int
    gross_completed_deal_value_minor: int
    total_simulated_buyer_fees_minor: int
    total_simulated_seller_fees_minor: int
    total_simulated_platform_revenue_minor: int


class DashboardResponse(BaseModel):
    simulated: Literal[True] = True
    organization_id: UUID
    buyer: BuyerMetrics
    seller: SellerMetrics
    platform_demo: PlatformMetrics | None


class LotMatch(BaseModel):
    lot_id: UUID
    lot: LotPublic
    match_type: Literal["DIRECT", "NEGOTIABLE"]
    match_score: int
    estimated_subtotal_minor: int
    estimated_buyer_fee_minor: int
    estimated_buyer_total_minor: int
    reasons: list[str]


class BuyerMatch(BaseModel):
    requirement_id: UUID
    requirement: RequirementPublic
    match_type: Literal["DIRECT", "NEGOTIABLE"]
    match_score: int
    estimated_subtotal_minor: int
    estimated_buyer_fee_minor: int
    estimated_buyer_total_minor: int
    reasons: list[str]


class DemoOrganization(Output):
    id: UUID
    name: str
    business_type: str
    city: str


class DemoIdentityOption(BaseModel):
    user_id: UUID
    user_name: str
    organization_id: UUID
    organization_name: str
    role: str


class OrganizationPrivate(DemoOrganization):
    area: str | None
    address: str | None
    contact_email: str
    contact_phone: str | None
    verification_status: str


class LotPrivate(LotPublic):
    min_unit_price_minor: int
    pickup_address: str
    original_description: str | None


class LotPatch(Input):
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    category: Category | None = None
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    original_description: str | None = Field(default=None, max_length=10000)
    quantity_total: Quantity | None = None
    unit: Unit | None = None
    asking_unit_price_minor: Money | None = None
    min_unit_price_minor: Money | None = None
    minimum_order_quantity: Quantity | None = None
    packaging_type: Literal["sealed"] | None = None
    storage_type: Literal["ambient", "chilled", "frozen"] | None = None
    manufacture_date: date | None = None
    expiry_date: date | None = None
    city: str | None = Field(default=None, min_length=1, max_length=100)
    pickup_area: str | None = Field(default=None, min_length=1, max_length=120)
    pickup_address: str | None = Field(default=None, min_length=1, max_length=2000)
    pickup_deadline: AwareDatetime | None = None
    resale_confirmed: bool | None = None
    information_confirmed: bool | None = None

    @field_validator("category", "unit", "city", mode="before")
    @classmethod
    def normalized(cls, value):
        return normalize(value) if isinstance(value, str) else value


class RequirementPatch(Input):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    original_description: str | None = Field(default=None, min_length=1, max_length=10000)
    category: Category | None = None
    required_quantity: Quantity | None = None
    unit: Unit | None = None
    max_total_budget_minor: Money | None = None
    min_shelf_life_days: int | None = Field(default=None, ge=0, le=3650)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    preferred_area: str | None = Field(default=None, max_length=120)

    @field_validator("category", "unit", "city", mode="before")
    @classmethod
    def normalized(cls, value):
        return normalize(value) if isinstance(value, str) else value


class PickupDetails(BaseModel):
    deal_id: UUID
    pickup_address: str
    pickup_area: str
    pickup_deadline: datetime
    simulated: Literal[True] = True
