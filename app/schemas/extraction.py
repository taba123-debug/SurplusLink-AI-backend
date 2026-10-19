from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.schemas.marketplace import Input, normalize, Quantity, Category, Unit

Rupees = Annotated[Decimal, Field(gt=0, le=10000000, decimal_places=2, allow_inf_nan=False)]


class ParseRequest(Input):
    text: str = Field(min_length=1, max_length=6000, validation_alias=AliasChoices("description", "text"))
    reference_date: date | None = None
    timezone: str | None = None

    @model_validator(mode="after")
    def valid_reference(self):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        if (self.reference_date is None) != (self.timezone is None):
            raise ValueError("Supply both reference_date and timezone")
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Invalid reference timezone") from None
        return self


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: dict[str, str] = Field(default_factory=dict)

    @field_validator("category", "unit", "city", mode="before", check_fields=False)
    @classmethod
    def normalized(cls, value):
        return normalize(value) if isinstance(value, str) else value

    @field_validator("unit", mode="before", check_fields=False)
    @classmethod
    def ambiguous_unit(cls, value):
        from typing import get_args
        return normalize(value) if isinstance(value, str) and normalize(value) in get_args(Unit) else None


class LotExtraction(Extraction):
    product_name: str | None = Field(default=None, max_length=200)
    category: Category | None = None
    quantity_total: Quantity | None = None
    unit: Unit | None = None
    asking_unit_price_rupees: Rupees | None = Field(default=None, exclude=True)
    min_unit_price_rupees: Rupees | None = Field(default=None, exclude=True)
    packaging_type: Literal["sealed"] | None = None
    storage_type: Literal["ambient", "chilled", "frozen"] | None = None
    expiry_date: date | None = None
    remaining_shelf_life_days: int | None = Field(default=None, ge=0, le=3650)
    relative_expiry_expression: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    pickup_area: str | None = Field(default=None, max_length=120)

    @computed_field
    @property
    def asking_unit_price_minor(self) -> int | None:
        return int(self.asking_unit_price_rupees * 100) if self.asking_unit_price_rupees is not None else None

    @computed_field
    @property
    def min_unit_price_minor(self) -> int | None:
        return int(self.min_unit_price_rupees * 100) if self.min_unit_price_rupees is not None else None


class RequirementExtraction(Extraction):
    title: str | None = Field(default=None, max_length=200)
    category: Category | None = None
    required_quantity: Quantity | None = None
    unit: Unit | None = None
    max_total_budget_rupees: Rupees | None = Field(default=None, exclude=True)
    min_shelf_life_days: int | None = Field(default=None, ge=0, le=3650)
    city: str | None = Field(default=None, max_length=100)
    preferred_area: str | None = Field(default=None, max_length=120)

    @computed_field
    @property
    def max_total_budget_minor(self) -> int | None:
        return int(self.max_total_budget_rupees * 100) if self.max_total_budget_rupees is not None else None


class LotParseResponse(BaseModel):
    provider: str
    model: str
    simulated: bool
    mode: Literal["live", "mock"]
    data: LotExtraction
    missing_fields: list[str]
    needs_review: Literal[True] = True
    persisted: Literal[False] = False


class RequirementParseResponse(BaseModel):
    provider: str
    model: str
    simulated: bool
    mode: Literal["live", "mock"]
    data: RequirementExtraction
    missing_fields: list[str]
    needs_review: Literal[True] = True
    persisted: Literal[False] = False
