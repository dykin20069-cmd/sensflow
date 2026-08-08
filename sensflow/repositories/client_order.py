"""Client Order repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import selectinload

from sensflow.domain.enums import ClientOrderStatus
from sensflow.infrastructure.database.models import ClientOrder, Customer
from sensflow.repositories.base import Repository


class ClientOrderRepository(Repository[ClientOrder]):
    """Load and persist Client Orders without deciding allowed state changes."""

    model = ClientOrder

    async def get_for_update(self, order_id: UUID) -> ClientOrder | None:
        statement = select(ClientOrder).where(ClientOrder.id == order_id).with_for_update()
        return await self.session.scalar(statement)

    async def get_details(self, order_id: UUID) -> ClientOrder | None:
        statement = (
            select(ClientOrder)
            .where(ClientOrder.id == order_id)
            .options(
                selectinload(ClientOrder.customer),
                selectinload(ClientOrder.timeline_events),
                selectinload(ClientOrder.marketplace_orders),
            )
        )
        return await self.session.scalar(statement)

    async def find_similar_active(
        self,
        *,
        username: str,
        place_id: int,
        requested_robux: int,
    ) -> ClientOrder | None:
        """Find the newest matching waiting or purchasing order."""
        statement = (
            select(ClientOrder)
            .join(ClientOrder.customer)
            .where(
                func.lower(Customer.current_username) == username.casefold(),
                ClientOrder.current_place_id == place_id,
                ClientOrder.requested_robux == requested_robux,
                ClientOrder.current_status.in_(
                    (ClientOrderStatus.PREORDER, ClientOrderStatus.PURCHASING)
                ),
            )
            .options(
                selectinload(ClientOrder.customer),
                selectinload(ClientOrder.timeline_events),
                selectinload(ClientOrder.marketplace_orders),
            )
            .order_by(ClientOrder.created_at.desc(), ClientOrder.id)
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def list_by_status(
        self,
        status: ClientOrderStatus,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ClientOrder]:
        statement = (
            select(ClientOrder)
            .where(ClientOrder.current_status == status)
            .options(selectinload(ClientOrder.customer))
            .order_by(ClientOrder.created_at.desc(), ClientOrder.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def count_by_status(self, status: ClientOrderStatus) -> int:
        statement = (
            select(func.count())
            .select_from(ClientOrder)
            .where(ClientOrder.current_status == status)
        )
        return int(await self.session.scalar(statement) or 0)

    async def list_expired_preferred_for_update(
        self,
        now: datetime,
        *,
        limit: int = 10_000,
    ) -> list[ClientOrder]:
        """Lock waiting orders whose preferred-rate window has elapsed."""
        statement = (
            select(ClientOrder)
            .where(
                ClientOrder.current_status == ClientOrderStatus.PREORDER,
                ClientOrder.fallback_active.is_(False),
                ClientOrder.preferred_expires_at.is_not(None),
                ClientOrder.preferred_expires_at <= now,
            )
            .order_by(ClientOrder.preferred_expires_at, ClientOrder.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def status_counts(self) -> dict[ClientOrderStatus, int]:
        statement = select(ClientOrder.current_status, func.count()).group_by(
            ClientOrder.current_status
        )
        rows = await self.session.execute(statement)
        return {status: int(count) for status, count in rows}

    async def list_for_customer(
        self,
        customer_id: UUID,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ClientOrder]:
        statement = (
            select(ClientOrder)
            .where(ClientOrder.customer_id == customer_id)
            .order_by(ClientOrder.created_at.desc(), ClientOrder.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def search(
        self,
        search_term: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ClientOrder]:
        pattern = f"%{search_term}%"
        statement = (
            select(ClientOrder)
            .join(ClientOrder.customer)
            .where(
                or_(
                    Customer.current_username.ilike(pattern),
                    cast(ClientOrder.id, String).ilike(pattern),
                )
            )
            .options(selectinload(ClientOrder.customer))
            .order_by(ClientOrder.created_at.desc(), ClientOrder.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def count_search(self, search_term: str) -> int:
        pattern = f"%{search_term}%"
        statement = (
            select(func.count())
            .select_from(ClientOrder)
            .join(ClientOrder.customer)
            .where(
                or_(
                    Customer.current_username.ilike(pattern),
                    cast(ClientOrder.id, String).ilike(pattern),
                )
            )
        )
        return int(await self.session.scalar(statement) or 0)

    async def delete(self, order: ClientOrder) -> None:
        """Delete an order after the application layer has established permission."""
        await self.session.delete(order)
        await self.session.flush()
