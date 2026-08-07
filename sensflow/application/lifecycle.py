"""Application startup and graceful shutdown lifecycle."""

import asyncio
import logging
import signal
from typing import Protocol

from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import AsyncEngine

from sensflow.application.automation_loop import AutomationLoop
from sensflow.application.recovery import RecoveryService
from sensflow.infrastructure.config import Settings
from sensflow.infrastructure.database.session import verify_database_connection

logger = logging.getLogger(__name__)


class AsyncCloseable(Protocol):
    """One owned async resource closed during application shutdown."""

    async def aclose(self) -> None: ...


class Application:
    """Own the lifecycle of the SensFlow process."""

    def __init__(
        self,
        settings: Settings,
        engine: AsyncEngine,
        bot: Bot,
        dispatcher: Dispatcher,
        external_resources: tuple[AsyncCloseable, ...] = (),
        *,
        recovery: RecoveryService | None = None,
        automation: AutomationLoop | None = None,
    ) -> None:
        self.settings = settings
        self.engine = engine
        self.bot = bot
        self.dispatcher = dispatcher
        self.recovery = recovery
        self.automation = automation
        self.external_resources = external_resources
        self._started = False
        self._closed = False
        self._polling_task: asyncio.Task[None] | None = None
        self._shutdown_requested = asyncio.Event()
        self._installed_signals: list[signal.Signals] = []

    async def start(self) -> None:
        """Start configured application components."""
        if self._started:
            return

        await verify_database_connection(self.engine)
        self._started = True
        if self.recovery is not None:
            await self.recovery.recover_incomplete_orders()
        if self.automation is not None:
            await self.automation.start()
        self._polling_task = asyncio.create_task(
            self.dispatcher.start_polling(
                self.bot,
                handle_signals=False,
                close_bot_session=False,
            ),
            name="telegram-polling",
        )
        self._polling_task.add_done_callback(self._polling_stopped)
        logger.info(
            "application_started environment=%s",
            self.settings.application.environment,
        )

    async def stop(self) -> None:
        """Stop application components in reverse startup order."""
        if self._closed:
            return

        polling_error: Exception | None = None
        if self._started:
            logger.info("application_stopping")
            if self._polling_task is not None and not self._polling_task.done():
                try:
                    await self.dispatcher.stop_polling()
                except RuntimeError:
                    self._polling_task.cancel()
            if self._polling_task is not None:
                try:
                    await self._polling_task
                except asyncio.CancelledError:
                    pass
                except Exception as error:  # surfaced after owned resources are closed
                    polling_error = error
            self._started = False

        automation_error: Exception | None = None
        if self.automation is not None:
            try:
                await self.automation.stop()
            except Exception as error:
                logger.exception("automation_stop_failed")
                automation_error = error

        resource_error: Exception | None = None
        for resource in reversed(self.external_resources):
            try:
                await resource.aclose()
            except Exception as error:  # close remaining owned resources before surfacing
                logger.exception("external_resource_close_failed")
                resource_error = resource_error or error
        await self.bot.session.close()
        await self.engine.dispose()
        self._closed = True
        logger.info("application_stopped")
        if polling_error is not None:
            raise polling_error
        if automation_error is not None:
            raise automation_error
        if resource_error is not None:
            raise resource_error

    def request_shutdown(self, reason: str) -> None:
        """Request an orderly shutdown once."""
        if self._shutdown_requested.is_set():
            return

        logger.info("shutdown_requested reason=%s", reason)
        self._shutdown_requested.set()

    async def run(self) -> None:
        """Run until a termination signal requests shutdown."""
        self._install_signal_handlers()
        try:
            await self.start()
            await self._shutdown_requested.wait()
        finally:
            await self.stop()
            self._remove_signal_handlers()

    def _polling_stopped(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            self.request_shutdown("telegram_polling_stopped")

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for received_signal in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    received_signal,
                    self.request_shutdown,
                    received_signal.name,
                )
            except (NotImplementedError, RuntimeError):
                continue
            self._installed_signals.append(received_signal)

    def _remove_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for installed_signal in self._installed_signals:
            loop.remove_signal_handler(installed_signal)
        self._installed_signals.clear()
