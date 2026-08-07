"""aiogram Dispatcher construction and router wiring."""

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from sensflow.application.ports import (
    CustomerUseCases,
    OrderUseCases,
    SettingsUseCases,
    StatisticsUseCases,
    SystemUseCases,
)
from sensflow.presentation.telegram.middleware import AuthorizationMiddleware
from sensflow.presentation.telegram.routers import root_router


def create_dispatcher(
    *,
    orders: OrderUseCases,
    customers: CustomerUseCases,
    settings: SettingsUseCases,
    statistics: StatisticsUseCases,
    system: SystemUseCases,
    operator_id: int,
) -> Dispatcher:
    """Create the single V1 dispatcher with in-process FSM storage."""
    dispatcher = Dispatcher(
        storage=MemoryStorage(),
        orders=orders,
        customers=customers,
        settings=settings,
        statistics=statistics,
        system=system,
    )
    authorization = AuthorizationMiddleware(operator_id)
    dispatcher.message.outer_middleware(authorization)
    dispatcher.callback_query.outer_middleware(authorization)
    dispatcher.include_router(root_router)
    return dispatcher
