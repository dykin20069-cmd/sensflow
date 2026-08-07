"""Marketplace Order repository."""

from uuid import UUID

from sqlalchemy import func, select

from sensflow.domain.enums import ClientOrderStatus, MarketplaceOrderStatus
from sensflow.infrastructure.database.models import ClientOrder, MarketplaceOrder
from sensflow.repositories.base import Repository


class MarketplaceOrderRepository(Repository[MarketplaceOrder]):
    """Load and persist RBXCreate attempt records without lifecycle decisions."""

    model = MarketplaceOrder

    async def get_by_external_id(self, rbxcreate_order_id: str) -> MarketplaceOrder | None:
        statement = select(MarketplaceOrder).where(
            MarketplaceOrder.rbxcreate_order_id == rbxcreate_order_id
        )
        return await self.session.scalar(statement)

    async def get_for_update(self, order_id: UUID) -> MarketplaceOrder | None:
        statement = (
            select(MarketplaceOrder).where(MarketplaceOrder.id == order_id).with_for_update()
        )
        return await self.session.scalar(statement)

    async def get_active_for_client_order(self, client_order_id: UUID) -> MarketplaceOrder | None:
        statement = select(MarketplaceOrder).where(
            MarketplaceOrder.client_order_id == client_order_id,
            MarketplaceOrder.marketplace_status == MarketplaceOrderStatus.ACTIVE,
        )
        return await self.session.scalar(statement)

    async def get_active_for_client_order_for_update(
        self,
        client_order_id: UUID,
    ) -> MarketplaceOrder | None:
        statement = (
            select(MarketplaceOrder)
            .where(
                MarketplaceOrder.client_order_id == client_order_id,
                MarketplaceOrder.marketplace_status == MarketplaceOrderStatus.ACTIVE,
            )
            .with_for_update()
        )
        return await self.session.scalar(statement)

    async def list_for_client_order(
        self,
        client_order_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[MarketplaceOrder]:
        statement = (
            select(MarketplaceOrder)
            .where(MarketplaceOrder.client_order_id == client_order_id)
            .order_by(MarketplaceOrder.created_at, MarketplaceOrder.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def list_by_status(
        self,
        status: MarketplaceOrderStatus,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[MarketplaceOrder]:
        statement = (
            select(MarketplaceOrder)
            .where(MarketplaceOrder.marketplace_status == status)
            .order_by(MarketplaceOrder.created_at, MarketplaceOrder.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def count_by_status(self, status: MarketplaceOrderStatus) -> int:
        statement = (
            select(func.count())
            .select_from(MarketplaceOrder)
            .where(MarketplaceOrder.marketplace_status == status)
        )
        return int(await self.session.scalar(statement) or 0)

    async def list_completed_for_unfinished_client_orders(
        self,
        *,
        limit: int = 100,
    ) -> list[MarketplaceOrder]:
        """Find completed attempts whose Client Order still needs finalization."""
        statement = (
            select(MarketplaceOrder)
            .join(MarketplaceOrder.client_order)
            .where(
                MarketplaceOrder.marketplace_status == MarketplaceOrderStatus.COMPLETED,
                ClientOrder.current_status == ClientOrderStatus.PURCHASING,
            )
            .order_by(MarketplaceOrder.completed_at, MarketplaceOrder.id)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)
