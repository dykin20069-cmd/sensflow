"""Customer and Customer history repositories."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from sensflow.infrastructure.database.models import (
    Customer,
    CustomerPlaceIDHistory,
    CustomerUsernameHistory,
)
from sensflow.repositories.base import Repository


class CustomerRepository(Repository[Customer]):
    """Load and persist Customers without applying Customer business rules."""

    model = Customer

    async def get_by_roblox_user_id(self, roblox_user_id: int) -> Customer | None:
        statement = select(Customer).where(Customer.roblox_user_id == roblox_user_id)
        return await self.session.scalar(statement)

    async def get_for_update(self, customer_id: UUID) -> Customer | None:
        statement = select(Customer).where(Customer.id == customer_id).with_for_update()
        return await self.session.scalar(statement)

    async def get_by_roblox_user_id_for_update(self, roblox_user_id: int) -> Customer | None:
        statement = (
            select(Customer).where(Customer.roblox_user_id == roblox_user_id).with_for_update()
        )
        return await self.session.scalar(statement)

    async def get_by_username(self, username: str) -> Customer | None:
        statement = select(Customer).where(Customer.current_username == username)
        return await self.session.scalar(statement)

    async def get_details(self, customer_id: UUID) -> Customer | None:
        statement = (
            select(Customer)
            .where(Customer.id == customer_id)
            .options(
                selectinload(Customer.username_history),
                selectinload(Customer.place_id_history),
                selectinload(Customer.client_orders),
            )
        )
        return await self.session.scalar(statement)

    async def search(
        self,
        search_term: str | None = None,
        *,
        archived: bool | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Customer]:
        statement = select(Customer)
        if search_term:
            statement = statement.where(Customer.current_username.ilike(f"%{search_term}%"))
        if archived is not None:
            statement = statement.where(Customer.archived.is_(archived))
        statement = (
            statement.order_by(Customer.last_activity.desc(), Customer.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def count(
        self,
        search_term: str | None = None,
        *,
        archived: bool | None = None,
    ) -> int:
        statement = select(func.count()).select_from(Customer)
        if search_term:
            statement = statement.where(Customer.current_username.ilike(f"%{search_term}%"))
        if archived is not None:
            statement = statement.where(Customer.archived.is_(archived))
        return int(await self.session.scalar(statement) or 0)


class CustomerUsernameHistoryRepository(Repository[CustomerUsernameHistory]):
    """Append and read chronological username history."""

    model = CustomerUsernameHistory

    async def list_for_customer(
        self,
        customer_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CustomerUsernameHistory]:
        statement = (
            select(CustomerUsernameHistory)
            .where(CustomerUsernameHistory.customer_id == customer_id)
            .order_by(CustomerUsernameHistory.created_at, CustomerUsernameHistory.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)


class CustomerPlaceIDHistoryRepository(Repository[CustomerPlaceIDHistory]):
    """Append and read chronological Place ID history."""

    model = CustomerPlaceIDHistory

    async def list_for_customer(
        self,
        customer_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CustomerPlaceIDHistory]:
        statement = (
            select(CustomerPlaceIDHistory)
            .where(CustomerPlaceIDHistory.customer_id == customer_id)
            .order_by(CustomerPlaceIDHistory.created_at, CustomerPlaceIDHistory.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)
