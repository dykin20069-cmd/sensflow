"""Application composition and process entry point."""

import asyncio
import logging

from sensflow.application.automation_loop import AutomationLoop
from sensflow.application.lifecycle import Application
from sensflow.application.marketplace_workflows import MarketplaceWorkflows
from sensflow.application.notifications import NotificationService
from sensflow.application.rbxcreate_bridge import RbxcreateBridge
from sensflow.application.recovery import RecoveryService
from sensflow.application.services import (
    CustomerApplicationService,
    OrderApplicationService,
    SettingsApplicationService,
    StatisticsApplicationService,
    SystemApplicationService,
)
from sensflow.domain.settings.service import SettingsDefaults
from sensflow.infrastructure.config import ConfigurationError, Settings, load_settings
from sensflow.infrastructure.database.session import (
    create_database_engine,
    create_session_factory,
)
from sensflow.infrastructure.logging import configure_logging
from sensflow.integrations.rbxcreate import RbxcrateDryRunGateway, RbxcrateGateway
from sensflow.integrations.roblox import RobloxPlaceResolver
from sensflow.presentation.telegram import create_bot, create_dispatcher
from sensflow.presentation.telegram.notifications import TelegramOperatorNotifier


def create_application(settings: Settings) -> Application:
    """Wire the concrete V1 process dependencies without a DI container."""
    engine = create_database_engine(settings.database)
    sessions = create_session_factory(engine)
    bot = create_bot(settings.telegram)
    roblox = RobloxPlaceResolver()
    rbxcrate_gateway = (
        RbxcrateDryRunGateway()
        if settings.rbxcrate.dry_run
        else RbxcrateGateway(
            api_key=settings.rbxcrate.api_key,
            base_url=settings.rbxcrate.base_url,
        )
    )
    rbxcrate_bridge = RbxcreateBridge(rbxcrate_gateway)
    settings_defaults = SettingsDefaults(
        maximum_purchase_rate=settings.marketplace.maximum_purchase_rate,
        automatic_reorder_enabled=settings.automation.automatic_reorder_enabled,
        automatic_reorder_interval_seconds=(settings.automation.automatic_reorder_interval_seconds),
        auto_requeue_delay_seconds=settings.automation.auto_requeue_delay_seconds,
        marketplace_monitoring_interval_seconds=(
            settings.marketplace.stock_monitoring_interval_seconds
        ),
        synchronization_interval_seconds=(settings.marketplace.synchronization_interval_seconds),
        marketplace_commission=settings.marketplace.commission_rate,
        usd_exchange_rate=settings.finance.usd_exchange_rate,
        telegram_notifications_enabled=settings.telegram.notifications_enabled,
        notification_categories=settings.telegram.notification_categories,
        application_timezone=settings.application.timezone,
    )
    marketplace_workflows = MarketplaceWorkflows(
        sessions,
        rbxcrate_bridge,
        settings_defaults=settings_defaults,
        minimum_purchase_rate=settings.marketplace.minimum_purchase_rate,
    )
    notifications = NotificationService(
        sessions,
        TelegramOperatorNotifier(bot, settings.telegram.operator_id),
        recipient=settings.telegram.operator_id,
    )
    automation = AutomationLoop(
        sessions,
        marketplace_workflows,
        settings_defaults=settings_defaults,
        notifications=notifications,
    )
    recovery = RecoveryService(sessions, marketplace_workflows)
    order_service = OrderApplicationService(
        sessions,
        roblox=roblox,
        settings_defaults=settings_defaults,
        operator_id=settings.telegram.operator_id,
        marketplace_workflows=marketplace_workflows,
    )
    dispatcher = create_dispatcher(
        orders=order_service,
        customers=CustomerApplicationService(
            sessions,
            roblox=roblox,
            operator_id=settings.telegram.operator_id,
        ),
        settings=SettingsApplicationService(
            sessions,
            defaults=settings_defaults,
            operator_id=settings.telegram.operator_id,
        ),
        statistics=StatisticsApplicationService(sessions),
        system=SystemApplicationService(
            engine,
            sessions=sessions,
            rbxcrate=rbxcrate_bridge,
            automation=automation,
            recovery=recovery,
            operator_id=settings.telegram.operator_id,
        ),
        operator_id=settings.telegram.operator_id,
    )
    return Application(
        settings,
        engine,
        bot,
        dispatcher,
        recovery=recovery,
        automation=automation,
        external_resources=(rbxcrate_gateway, roblox),
    )


def main() -> int:
    """Load configuration and run the application until shutdown."""
    try:
        settings = load_settings()
    except ConfigurationError as error:
        configure_logging("ERROR")
        logging.getLogger(__name__).error("configuration_failed: %s", error)
        return 2

    configure_logging(settings.logging.level)
    logger = logging.getLogger(__name__)

    try:
        asyncio.run(create_application(settings).run())
    except KeyboardInterrupt:
        logger.info("application_interrupted")
    except Exception:
        logger.exception("application_crashed")
        return 1

    return 0
