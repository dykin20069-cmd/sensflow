"""Internal application boundary for future marketplace callbacks."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sensflow.application.marketplace_workflows import MarketplaceWorkflows
from sensflow.repositories import MarketplaceOrderRepository

SessionFactory = async_sessionmaker[AsyncSession]


class MarketplaceCallbackService:
    """Translate an external order reference into normal synchronization."""

    def __init__(
        self,
        sessions: SessionFactory,
        workflows: MarketplaceWorkflows,
    ) -> None:
        self._sessions = sessions
        self._workflows = workflows

    async def handle_order_update(self, external_order_id: str) -> bool:
        """Synchronize a known external order and report whether it exists."""
        async with self._sessions() as session:
            marketplace_order = await MarketplaceOrderRepository(session).get_by_external_id(
                external_order_id
            )
            if marketplace_order is None:
                return False
            marketplace_order_id = marketplace_order.id
        await self._workflows.synchronize_marketplace_order(marketplace_order_id)
        return True
