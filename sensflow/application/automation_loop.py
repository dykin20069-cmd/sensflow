"""Minimal in-process polling for marketplace synchronization and PreOrders."""

import asyncio
import logging
from contextlib import suppress

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sensflow.application.marketplace_workflows import MarketplaceWorkflows
from sensflow.domain.enums import ClientOrderStatus, MarketplaceOrderStatus
from sensflow.domain.settings.service import SettingsDefaults, create_settings
from sensflow.infrastructure.database.models import SystemSettings
from sensflow.repositories import (
    ClientOrderRepository,
    MarketplaceOrderRepository,
    SystemSettingsRepository,
)

logger = logging.getLogger(__name__)

SessionFactory = async_sessionmaker[AsyncSession]


class AutomationLoop:
    """Run sequential polling passes inside one owned asyncio task."""

    def __init__(
        self,
        sessions: SessionFactory,
        workflows: MarketplaceWorkflows,
        *,
        settings_defaults: SettingsDefaults | None = None,
    ) -> None:
        self._sessions = sessions
        self._workflows = workflows
        self._settings_defaults = settings_defaults
        self._shutdown = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the loop once without blocking application startup."""
        if self._task is not None and not self._task.done():
            return
        self._shutdown.clear()
        self._task = asyncio.create_task(self._run(), name="marketplace-automation")

    @property
    def is_running(self) -> bool:
        """Report whether the owned polling task is currently alive."""
        return self._task is not None and not self._task.done()

    async def stop(self) -> None:
        """Wake and await the owned loop task."""
        if self._task is None:
            return
        self._shutdown.set()
        try:
            await self._task
        finally:
            self._task = None

    async def run_synchronization_pass(self) -> int:
        """Synchronize every active attempt sequentially and isolate failures."""
        async with self._sessions() as session:
            repository = MarketplaceOrderRepository(session)
            active_attempts = await repository.list_by_status(
                MarketplaceOrderStatus.ACTIVE,
                limit=10_000,
            )
            unfinished_completions = await repository.list_completed_for_unfinished_client_orders(
                limit=10_000
            )
            attempt_ids = tuple(
                attempt.id for attempt in (*active_attempts, *unfinished_completions)
            )
        for attempt_id in attempt_ids:
            try:
                await self._workflows.synchronize_marketplace_order(attempt_id)
            except Exception:
                logger.exception(
                    "marketplace_synchronization_failed",
                    extra={"marketplace_order_id": str(attempt_id)},
                )
        return len(active_attempts)

    async def run_reorder_pass(self) -> None:
        """Attempt each waiting order sequentially and isolate failures."""
        async with self._sessions() as session:
            orders = await ClientOrderRepository(session).list_by_status(
                ClientOrderStatus.PREORDER,
                limit=10_000,
            )
            order_ids = tuple(order.id for order in orders)
        for order_id in order_ids:
            try:
                await self._workflows.start_purchase(order_id)
            except Exception:
                logger.exception(
                    "automatic_reorder_failed",
                    extra={"order_id": str(order_id)},
                )

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        next_sync = 0.0
        next_reorder = 0.0
        while not self._shutdown.is_set():
            try:
                settings = await self._get_settings()
                now = loop.time()
                if now >= next_sync:
                    await self.run_synchronization_pass()
                    next_sync = loop.time() + settings.synchronization_interval_seconds
                if now >= next_reorder:
                    if settings.automatic_reorder_enabled:
                        await self.run_reorder_pass()
                    next_reorder = loop.time() + settings.automatic_reorder_interval_seconds
                delay = max(0.0, min(next_sync, next_reorder) - loop.time())
            except Exception:
                logger.exception("automation_iteration_failed")
                delay = 1.0
            with suppress(TimeoutError):
                await asyncio.wait_for(self._shutdown.wait(), timeout=delay)

    async def _get_settings(self) -> SystemSettings:
        async with self._sessions.begin() as session:
            repository = SystemSettingsRepository(session)
            settings = await repository.get_current()
            if settings is not None:
                return settings
            if self._settings_defaults is None:
                raise RuntimeError("System Settings are not initialized")
            return await repository.save(create_settings(self._settings_defaults))
