"""Validated application query models."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from sensflow.domain.enums import ClientOrderStatus, StatisticsPeriod

SearchTerm = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Query(BaseModel):
    """Base for immutable query input."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PaginatedQuery(Query):
    """One-based bounded page input shared by list queries."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=50)


class ListOrdersQuery(PaginatedQuery):
    """List Client Orders in one documented lifecycle status."""

    status: ClientOrderStatus


class SearchOrdersQuery(PaginatedQuery):
    """Search Client Orders by UUID text or current Customer username."""

    search_term: SearchTerm


class GetOrderQuery(Query):
    """Load one Client Order details screen."""

    order_id: UUID


class SearchCustomersQuery(PaginatedQuery):
    """Search current Customer usernames, optionally including archived Customers."""

    search_term: SearchTerm | None = None
    archived: bool | None = None


class GetCustomerQuery(Query):
    """Load one Customer details screen."""

    customer_id: UUID


class GetStatisticsQuery(Query):
    """Load the latest projection for one documented reporting period."""

    period: StatisticsPeriod
