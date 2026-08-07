"""Telegram router composition."""

from aiogram import Router

from sensflow.presentation.telegram.errors import handle_unexpected_error
from sensflow.presentation.telegram.routers.create_order import router as create_order_router
from sensflow.presentation.telegram.routers.customers import router as customers_router
from sensflow.presentation.telegram.routers.fallback import router as fallback_router
from sensflow.presentation.telegram.routers.main import router as main_router
from sensflow.presentation.telegram.routers.orders import router as orders_router
from sensflow.presentation.telegram.routers.settings import router as settings_router
from sensflow.presentation.telegram.routers.statistics import router as statistics_router

root_router = Router(name="root")
root_router.include_routers(
    main_router,
    create_order_router,
    orders_router,
    customers_router,
    settings_router,
    statistics_router,
    fallback_router,
)
root_router.errors.register(handle_unexpected_error)
