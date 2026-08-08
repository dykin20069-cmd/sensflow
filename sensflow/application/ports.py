"""Use-case ports consumed by the Telegram presentation layer."""

from typing import Protocol

from sensflow.application.commands import (
    ArchiveCustomerCommand,
    CreateOrderCommand,
    CustomerActionCommand,
    EditDraftCommand,
    OrderActionCommand,
    PrepareCreateOrderCommand,
    SystemActionCommand,
    UpdatePlaceIDCommand,
    UpdateSettingCommand,
)
from sensflow.application.dto import (
    ActionResultDTO,
    CurrentStockDTO,
    CustomerDetailDTO,
    CustomerSummaryDTO,
    OrderDetailDTO,
    OrderStatusCountsDTO,
    OrderSummaryDTO,
    PageDTO,
    PlaceIDSelectionDTO,
    SettingsDTO,
    StatisticsDTO,
    StockAvailabilityDTO,
    SystemStatusDTO,
    TimelineEventDTO,
)
from sensflow.application.queries import (
    FindSimilarOrderQuery,
    GetCustomerQuery,
    GetOrderQuery,
    GetStatisticsQuery,
    ListOrdersQuery,
    SearchCustomersQuery,
    SearchOrdersQuery,
)


class OrderUseCases(Protocol):
    """Order operations available to presentation without Telegram dependencies."""

    async def get_status_counts(self) -> OrderStatusCountsDTO: ...

    async def list_orders(self, query: ListOrdersQuery) -> PageDTO[OrderSummaryDTO]: ...

    async def search_orders(self, query: SearchOrdersQuery) -> PageDTO[OrderSummaryDTO]: ...

    async def get_order(self, query: GetOrderQuery) -> OrderDetailDTO: ...

    async def find_similar_order(self, query: FindSimilarOrderQuery) -> OrderDetailDTO | None: ...

    async def get_current_stock(self) -> CurrentStockDTO: ...

    async def check_stock(self, command: PrepareCreateOrderCommand) -> StockAvailabilityDTO: ...

    async def get_timeline(self, query: GetOrderQuery) -> tuple[TimelineEventDTO, ...]: ...

    async def prepare_create_order(
        self, command: PrepareCreateOrderCommand
    ) -> PlaceIDSelectionDTO: ...

    async def refresh_public_places(
        self, command: PrepareCreateOrderCommand
    ) -> PlaceIDSelectionDTO: ...

    async def create_order(self, command: CreateOrderCommand) -> ActionResultDTO: ...

    async def edit_draft(self, command: EditDraftCommand) -> ActionResultDTO: ...

    async def delete_draft(self, command: OrderActionCommand) -> ActionResultDTO: ...

    async def confirm_payment(self, command: OrderActionCommand) -> ActionResultDTO: ...

    async def start_purchase(self, command: OrderActionCommand) -> ActionResultDTO: ...

    async def send_to_preorder(self, command: OrderActionCommand) -> ActionResultDTO: ...

    async def manual_reorder(self, command: OrderActionCommand) -> ActionResultDTO: ...

    async def toggle_auto_requeue(self, command: OrderActionCommand) -> ActionResultDTO: ...

    async def cancel_order(self, command: OrderActionCommand) -> ActionResultDTO: ...

    async def refresh_order(self, command: OrderActionCommand) -> ActionResultDTO: ...

    async def repeat_order(self, command: OrderActionCommand) -> ActionResultDTO: ...


class CustomerUseCases(Protocol):
    """Customer operations available to presentation."""

    async def search_customers(
        self, query: SearchCustomersQuery
    ) -> PageDTO[CustomerSummaryDTO]: ...

    async def get_customer(self, query: GetCustomerQuery) -> CustomerDetailDTO: ...

    async def refresh_customer(self, command: CustomerActionCommand) -> ActionResultDTO: ...

    async def update_place_id(self, command: UpdatePlaceIDCommand) -> ActionResultDTO: ...

    async def archive_customer(self, command: ArchiveCustomerCommand) -> ActionResultDTO: ...


class SettingsUseCases(Protocol):
    """System Settings operations available to presentation."""

    async def get_settings(self) -> SettingsDTO | None: ...

    async def update_setting(self, command: UpdateSettingCommand) -> ActionResultDTO: ...


class StatisticsUseCases(Protocol):
    """Persisted statistics reads available to presentation."""

    async def get_statistics(self, query: GetStatisticsQuery) -> StatisticsDTO | None: ...


class SystemUseCases(Protocol):
    """Non-sensitive application availability query."""

    async def get_status(self) -> SystemStatusDTO: ...

    async def run_recovery_now(self, command: SystemActionCommand) -> ActionResultDTO: ...

    async def run_sync_pass_now(self, command: SystemActionCommand) -> ActionResultDTO: ...
