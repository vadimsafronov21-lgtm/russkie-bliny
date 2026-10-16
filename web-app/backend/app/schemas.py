from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Quantity = Annotated[Decimal, Field(gt=0, le=1000000, max_digits=12, decimal_places=3)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class Line(Input):
    ingredient_id: str = Field(min_length=1, max_length=40)
    quantity: Quantity


class CreateRequest(Input):
    point_id: str
    warehouse_id: str = "warehouse"
    lines: list[Line] = Field(min_length=1, max_length=30)
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def unique_lines(self):
        if len({line.ingredient_id for line in self.lines}) != len(self.lines):
            raise ValueError("Ингредиент повторяется в заявке")
        return self


class Transition(Input):
    version: int = Field(ge=1)
    status: Literal["accepted", "packing", "sent", "cancelled"]


class Receive(Input):
    version: int = Field(ge=1)
    lines: list[Line] = Field(min_length=1, max_length=30)
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def unique_lines(self):
        if len({line.ingredient_id for line in self.lines}) != len(self.lines):
            raise ValueError("Ингредиент повторяется в приёмке")
        return self


class DemoSale(Input):
    event_id: str = Field(min_length=1, max_length=100)
    point_id: str
    item_id: str
    quantity: int = Field(ge=1, le=1000)
    day: date
    kind: Literal["sale", "cancel_before", "refund_prepared"] = "sale"
    original_id: str | None = None
