
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductFilters(BaseModel):
    """Optional attributes used to filter matching products."""

    model_config = ConfigDict(extra="forbid")

    color: str | None = None
    brand: str | None = None
    size: str | None = None
    gender: str | None = None
    occasion: str | None = None


class Budget(BaseModel):
    """Customer's requested price range."""

    model_config = ConfigDict(extra="forbid")

    min: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)
    currency: str = "EGP"

    @model_validator(mode="after")
    def validate_price_range(self):
        """Ensure the minimum price does not exceed the maximum."""
        if (
            self.min is not None
            and self.max is not None
            and self.min > self.max
        ):
            raise ValueError(
                "Minimum budget cannot be greater than maximum budget."
            )

        return self


class ShoppingRequest(BaseModel):
    """Structured representation of a customer's shopping request."""

    model_config = ConfigDict(extra="forbid")  # forbid : It tells Pydantic to reject fields that are not defined in this model

    category: str = Field(min_length=1)
    search_query: str = Field(min_length=1)
    filters: ProductFilters = Field(default_factory=ProductFilters) #this is the optional attribute
    """default_factory tells Pydantic: if the caller doesn't provide filters, 
    create a new, empty ProductFilters object automatically."""
    budget: Budget = Field(default_factory=Budget)
    language: Literal["en"] = "en"


"""
example of a JSON object :
{
  "category": "handbag",
  "search_query": "black handbag for university",
  "filters": {
    "color": "black",
    "brand": null,
    "size": null,
    "gender": null,
    "occasion": "university"
  },
  "budget": {
    "min": null,
    "max": 1500,
    "currency": "EGP"
  },
  "language": "en"
}

"""