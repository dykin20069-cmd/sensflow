"""Concrete application services coordinating repository-backed use cases."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import NoReturn

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sensflow.application.automation_loop import AutomationLoop
from sensflow.application.commands import (
    ArchiveCustomerCommand,
    CreateOrderCommand,
    CustomerActionCommand,
    EditDraftCommand,
    FinalizePurchaseCommand,
    OrderActionCommand,
    PrepareCreateOrderCommand,
    SystemActionCommand,
    UpdatePlaceIDCommand,
    UpdateSettingCommand,
)
from sensflow.application.dto import (
    ActionResultDTO,
    CurrentStockDTO,
    CustomerAction,
    CustomerDetailDTO,
    CustomerSummaryDTO,
    OrderAction,
    OrderDetailDTO,
    OrderStatusCountsDTO,
    OrderSummaryDTO,
    PageDTO,
    PlaceIDHistoryDTO,
    PlaceIDSelectionDTO,
    PublicPlaceDTO,
    RememberedPlaceDTO,
    SettingsDTO,
    StatisticsDTO,
    StockAvailabilityDTO,
    SystemStatusDTO,
    TimelineEventDTO,
    UsernameHistoryDTO,
)
from sensflow.application.errors import (
    AuthorizationError,
    ConflictError,
    FeatureUnavailableError,
    InputValidationError,
    MarketplaceIntegrationError,
    NotFoundError,
)
from sensflow.application.gateways import (
    MarketplaceGateway,
    RobloxGateway,
    UnavailableMarketplaceGateway,
    UnavailableRobloxGateway,
)
from sensflow.application.marketplace_workflows import MarketplaceWorkflows
from sensflow.application.queries import (
    FindSimilarOrderQuery,
    GetCustomerQuery,
    GetOrderQuery,
    GetStatisticsQuery,
    ListOrdersQuery,
    SearchCustomersQuery,
    SearchOrdersQuery,
)
from sensflow.application.rbxcreate_bridge import RbxcreateBridge
from sensflow.application.recovery import RecoveryService
from sensflow.domain.customer.service import (
    RobloxIdentity,
    create_customer,
    create_manual_customer,
    refresh_identity,
    update_place_id,
)
from sensflow.domain.customer.service import (
    archive_customer as apply_customer_archive,
)
from sensflow.domain.enums import ClientOrderStatus, MarketplaceOrderStatus, TimelineEventType
from sensflow.domain.errors import DomainConflictError, DomainValidationError
from sensflow.domain.finance.service import (
    calculate_customer_receives,
    calculate_financial_snapshot,
)
from sensflow.domain.marketplace.service import (
    cancel_marketplace_order,
    complete_marketplace_order,
    create_marketplace_order,
)
from sensflow.domain.order.service import (
    cancel_order as apply_order_cancellation,
)
from sensflow.domain.order.service import complete_order as apply_order_completion
from sensflow.domain.order.service import (
    create_draft,
    edit_draft,
    enter_preorder,
    start_purchasing,
)
from sensflow.domain.order.timeline import create_timeline_event
from sensflow.domain.settings.service import (
    SettingsDefaults,
    create_settings,
)
from sensflow.domain.settings.service import (
    update_setting as apply_setting_update,
)
from sensflow.infrastructure.database.base import utc_now
from sensflow.infrastructure.database.models import (
    ClientOrder,
    Customer,
    Statistics,
    SystemSettings,
    TimelineEvent,
    UserPlaceCache,
)
from sensflow.infrastructure.database.session import verify_database_connection
from sensflow.repositories import (
    ClientOrderRepository,
    CustomerPlaceIDHistoryRepository,
    CustomerRepository,
    CustomerUsernameHistoryRepository,
    MarketplaceOrderRepository,
    StatisticsRepository,
    SystemSettingsRepository,
    TimelineEventRepository,
    UserPlaceCacheRepository,
)

SessionFactory = async_sessionmaker[AsyncSession]
Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)
MAX_PUBLIC_PLACE_OPTIONS = 10


def _bounded_page(requested_page: int, page_size: int, total_items: int) -> int:
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    return min(requested_page, total_pages)


def _order_actions(
    status: ClientOrderStatus,
    *,
    automatic_requeue_enabled: bool = True,
) -> tuple[OrderAction, ...]:
    if status is ClientOrderStatus.DRAFT:
        return (
            OrderAction.CONFIRM_PAYMENT,
            OrderAction.EDIT_DRAFT,
            OrderAction.DELETE_DRAFT,
            OrderAction.TIMELINE,
        )
    if status is ClientOrderStatus.PREORDER:
        return (
            OrderAction.START_PURCHASE,
            OrderAction.FORCE_PURCHASE,
            OrderAction.CANCEL,
            OrderAction.TIMELINE,
        )
    if status is ClientOrderStatus.PURCHASING:
        return (
            OrderAction.MANUAL_REORDER,
            (
                OrderAction.DISABLE_AUTO_REQUEUE
                if automatic_requeue_enabled
                else OrderAction.ENABLE_AUTO_REQUEUE
            ),
            OrderAction.CANCEL,
            OrderAction.REFRESH,
            OrderAction.TIMELINE,
        )
    return (OrderAction.TIMELINE,)


def _order_summary(order: ClientOrder, customer_username: str | None = None) -> OrderSummaryDTO:
    username = customer_username or order.customer.current_username
    return OrderSummaryDTO(
        id=order.id,
        customer_username=username,
        status=order.current_status,
        requested_robux=order.requested_robux,
        created_at=order.created_at,
    )


def _timeline_event(event: TimelineEvent) -> TimelineEventDTO:
    return TimelineEventDTO(
        event_type=event.event_type,
        description=event.description,
        created_at=event.created_at,
    )


def _order_detail(
    order: ClientOrder,
    *,
    remembered_place: bool = False,
    reorder_interval: Decimal | None = None,
    now: datetime | None = None,
) -> OrderDetailDTO:
    preorder_started_at = next(
        (
            event.created_at
            for event in reversed(order.timeline_events)
            if event.event_type is TimelineEventType.PREORDER_CREATED
        ),
        order.created_at,
    )
    current_attempt = next(
        (
            attempt
            for attempt in reversed(order.marketplace_orders)
            if attempt.marketplace_status is MarketplaceOrderStatus.ACTIVE
        ),
        order.marketplace_orders[-1] if order.marketplace_orders else None,
    )
    completed_attempt = next(
        (
            attempt
            for attempt in reversed(order.marketplace_orders)
            if attempt.marketplace_status is MarketplaceOrderStatus.COMPLETED
        ),
        None,
    )
    return OrderDetailDTO(
        id=order.id,
        customer_username=order.customer.current_username,
        status=order.current_status,
        requested_robux=order.requested_robux,
        customer_receives=(
            order.customer_receives
            if order.customer_receives is not None
            else calculate_customer_receives(
                order.requested_robux,
                tax_rate=Decimal("0.30"),
                rounding=ROUND_DOWN,
            )
        ),
        current_place_id=order.current_place_id,
        marketplace_rate_limit=order.marketplace_rate_limit,
        marketplace_cost=order.marketplace_cost,
        marketplace_commission=order.marketplace_commission,
        final_cost_usd=order.final_cost_usd,
        final_cost_local_currency=order.final_cost_local_currency,
        created_at=order.created_at,
        completed_at=order.completed_at,
        timeline=tuple(_timeline_event(event) for event in order.timeline_events),
        marketplace_rate=(None if completed_attempt is None else completed_attempt.purchase_rate),
        marketplace_status=(
            None if current_attempt is None else current_attempt.marketplace_status
        ),
        marketplace_order_reference=(
            None if current_attempt is None else current_attempt.rbxcreate_order_id
        ),
        waiting_seconds=(
            None
            if order.current_status is not ClientOrderStatus.PREORDER or now is None
            else max(0, int((now - preorder_started_at).total_seconds()))
        ),
        next_automatic_retry_seconds=(
            reorder_interval if order.current_status is ClientOrderStatus.PREORDER else None
        ),
        remembered_place=remembered_place,
        automatic_requeue_enabled=(order.automatic_requeue_enabled is not False),
        requeue_attempts=order.requeue_attempts or 0,
        last_requeue_at=order.last_requeue_at,
        available_actions=_order_actions(
            order.current_status,
            automatic_requeue_enabled=(order.automatic_requeue_enabled is not False),
        ),
    )


def _customer_summary(customer: Customer) -> CustomerSummaryDTO:
    return CustomerSummaryDTO(
        id=customer.id,
        username=customer.current_username,
        roblox_user_id=customer.roblox_user_id,
        current_place_id=customer.current_place_id,
        archived=customer.archived,
    )


def _customer_detail(customer: Customer) -> CustomerDetailDTO:
    actions = [CustomerAction.REFRESH, CustomerAction.UPDATE_PLACE_ID]
    if not customer.archived:
        actions.append(CustomerAction.ARCHIVE)
    return CustomerDetailDTO(
        id=customer.id,
        username=customer.current_username,
        roblox_user_id=customer.roblox_user_id,
        current_place_id=customer.current_place_id,
        archived=customer.archived,
        notes=customer.notes,
        username_history=tuple(
            UsernameHistoryDTO(username=item.username, created_at=item.created_at)
            for item in customer.username_history
        ),
        place_id_history=tuple(
            PlaceIDHistoryDTO(place_id=item.place_id, created_at=item.created_at)
            for item in customer.place_id_history
        ),
        orders=tuple(
            _order_summary(order, customer.current_username) for order in customer.client_orders
        ),
        available_actions=tuple(actions),
    )


def _settings(settings: SystemSettings) -> SettingsDTO:
    return SettingsDTO(
        maximum_purchase_rate=settings.maximum_purchase_rate,
        automatic_reorder_enabled=settings.automatic_reorder_enabled,
        automatic_reorder_interval_seconds=settings.automatic_reorder_interval_seconds,
        auto_requeue_delay_seconds=settings.auto_requeue_delay_seconds,
        marketplace_monitoring_interval_seconds=settings.marketplace_monitoring_interval_seconds,
        synchronization_interval_seconds=settings.synchronization_interval_seconds,
        marketplace_commission=settings.marketplace_commission,
        usd_exchange_rate=settings.usd_exchange_rate,
        telegram_notifications_enabled=settings.telegram_notifications_enabled,
        notification_categories=tuple(settings.notification_categories),
        application_timezone=settings.application_timezone,
    )


def _statistics(statistics: Statistics) -> StatisticsDTO:
    return StatisticsDTO(
        period=statistics.period,
        period_start=statistics.period_start,
        total_orders=statistics.total_orders,
        draft_orders=statistics.draft_orders,
        preorder_orders=statistics.preorder_orders,
        purchasing_orders=statistics.purchasing_orders,
        completed_orders=statistics.completed_orders,
        cancelled_orders=statistics.cancelled_orders,
        total_purchased_robux=statistics.total_purchased_robux,
        total_amount_paid=statistics.total_amount_paid,
        average_marketplace_rate=statistics.average_marketplace_rate,
        average_purchase_cost=statistics.average_purchase_cost,
        total_marketplace_commission=statistics.total_marketplace_commission,
    )


def _authorize(actual_operator_id: int, configured_operator_id: int | None) -> None:
    if configured_operator_id is None or actual_operator_id != configured_operator_id:
        raise AuthorizationError("The caller is not the configured operator")


def _raise_domain_error(error: DomainValidationError | DomainConflictError) -> NoReturn:
    if isinstance(error, DomainValidationError):
        raise InputValidationError((str(error),)) from error
    raise ConflictError(str(error)) from error


async def _get_or_create_settings(
    repository: SystemSettingsRepository,
    defaults: SettingsDefaults | None,
    *,
    for_update: bool,
) -> SystemSettings:
    getter = repository.get_current_for_update if for_update else repository.get_current
    settings = await getter()
    if settings is not None:
        return settings
    if defaults is None:
        raise FeatureUnavailableError("System Settings initialization")
    return await repository.save(create_settings(defaults))


class OrderApplicationService:
    """Coordinate Customer resolution and the Client Order lifecycle."""

    def __init__(
        self,
        sessions: SessionFactory,
        *,
        roblox: RobloxGateway | None = None,
        marketplace: MarketplaceGateway | None = None,
        settings_defaults: SettingsDefaults | None = None,
        operator_id: int | None = None,
        marketplace_workflows: MarketplaceWorkflows | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._sessions = sessions
        self._roblox = roblox or UnavailableRobloxGateway()
        self._marketplace = marketplace or UnavailableMarketplaceGateway()
        self._settings_defaults = settings_defaults
        self._operator_id = operator_id
        self._marketplace_workflows = marketplace_workflows
        self._clock = clock

    async def get_status_counts(self) -> OrderStatusCountsDTO:
        async with self._sessions() as session:
            stored_counts = await ClientOrderRepository(session).status_counts()
        counts = {status: stored_counts.get(status, 0) for status in ClientOrderStatus}
        return OrderStatusCountsDTO(counts=counts)

    async def list_orders(self, query: ListOrdersQuery) -> PageDTO[OrderSummaryDTO]:
        async with self._sessions() as session:
            repository = ClientOrderRepository(session)
            total_items = await repository.count_by_status(query.status)
            page_number = _bounded_page(query.page, query.page_size, total_items)
            orders = await repository.list_by_status(
                query.status,
                offset=(page_number - 1) * query.page_size,
                limit=query.page_size,
            )
        return PageDTO(
            items=tuple(_order_summary(order) for order in orders),
            page=page_number,
            page_size=query.page_size,
            total_items=total_items,
        )

    async def search_orders(self, query: SearchOrdersQuery) -> PageDTO[OrderSummaryDTO]:
        async with self._sessions() as session:
            repository = ClientOrderRepository(session)
            total_items = await repository.count_search(query.search_term)
            page_number = _bounded_page(query.page, query.page_size, total_items)
            orders = await repository.search(
                query.search_term,
                offset=(page_number - 1) * query.page_size,
                limit=query.page_size,
            )
        return PageDTO(
            items=tuple(_order_summary(order) for order in orders),
            page=page_number,
            page_size=query.page_size,
            total_items=total_items,
        )

    async def get_order(self, query: GetOrderQuery) -> OrderDetailDTO:
        async with self._sessions() as session:
            order = await ClientOrderRepository(session).get_details(query.order_id)
            if order is None:
                raise NotFoundError("Client Order")
            remembered = await UserPlaceCacheRepository(session).get_by_username(
                order.customer.current_username
            )
            settings = await SystemSettingsRepository(session).get_current()
            return _order_detail(
                order,
                remembered_place=(
                    remembered is not None and remembered.place_id == order.current_place_id
                ),
                reorder_interval=(
                    None if settings is None else settings.automatic_reorder_interval_seconds
                ),
                now=self._clock(),
            )

    async def find_similar_order(
        self,
        query: FindSimilarOrderQuery,
    ) -> OrderDetailDTO | None:
        async with self._sessions() as session:
            order = await ClientOrderRepository(session).find_similar_active(
                username=query.username,
                place_id=query.place_id,
                requested_robux=query.requested_robux,
            )
            return None if order is None else _order_detail(order)

    async def get_current_stock(self) -> CurrentStockDTO:
        if self._marketplace_workflows is None:
            raise FeatureUnavailableError("Marketplace stock lookup")
        return await self._marketplace_workflows.get_current_stock()

    async def check_stock(
        self,
        command: PrepareCreateOrderCommand,
    ) -> StockAvailabilityDTO:
        if self._marketplace_workflows is None:
            raise FeatureUnavailableError("Marketplace stock lookup")
        return await self._marketplace_workflows.check_stock(command.requested_robux)

    async def get_timeline(self, query: GetOrderQuery) -> tuple[TimelineEventDTO, ...]:
        return (await self.get_order(query)).timeline

    async def prepare_create_order(
        self,
        command: PrepareCreateOrderCommand,
    ) -> PlaceIDSelectionDTO:
        async with self._sessions() as session:
            remembered = await UserPlaceCacheRepository(session).get_by_username(command.username)
        if remembered is not None:
            logger.info(
                "place_resolver_cache_hit",
                extra={"username": command.username, "place_id": remembered.place_id},
            )
            return PlaceIDSelectionDTO(
                username=command.username,
                requested_robux=command.requested_robux,
                remembered_place=RememberedPlaceDTO(
                    place_id=remembered.place_id,
                    place_name=remembered.place_name,
                ),
            )
        return await self.refresh_public_places(command)

    async def refresh_public_places(
        self,
        command: PrepareCreateOrderCommand,
    ) -> PlaceIDSelectionDTO:
        resolution = await self._roblox.resolve_public_places(command.username)
        logger.info(
            "place_resolver_public_places_found",
            extra={"username": resolution.identity.username, "count": len(resolution.places)},
        )
        return PlaceIDSelectionDTO(
            username=resolution.identity.username,
            requested_robux=command.requested_robux,
            roblox_user_id=resolution.identity.user_id,
            public_places=tuple(
                PublicPlaceDTO(
                    place_id=place.place_id,
                    universe_id=place.universe_id,
                    place_name=place.place_name,
                    visits=place.visits,
                    updated_at=place.updated_at,
                )
                for place in resolution.places[:MAX_PUBLIC_PLACE_OPTIONS]
            ),
        )

    async def create_order(self, command: CreateOrderCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        for attempt_number in range(2):
            try:
                order = await self._create_order_transaction(command)
            except (DomainValidationError, DomainConflictError) as error:
                _raise_domain_error(error)
            except IntegrityError as error:
                if attempt_number == 0:
                    continue
                raise ConflictError(
                    "The Customer or order changed concurrently; please retry"
                ) from error
            else:
                break
        return ActionResultDTO(
            message=f"Draft order {order.id} was created.",
            order_id=order.id,
        )

    async def _create_order_transaction(
        self,
        command: CreateOrderCommand,
    ) -> ClientOrder:
        async with self._sessions.begin() as session:
            customers = CustomerRepository(session)
            now = self._clock()
            identity = (
                None
                if command.roblox_user_id is None
                else RobloxIdentity(command.roblox_user_id, command.username)
            )
            customer = (
                None
                if identity is None
                else await customers.get_by_roblox_user_id_for_update(identity.user_id)
            )
            if customer is None:
                customer = await customers.get_by_username_for_update(command.username)
            if customer is None:
                customer = await customers.save(
                    create_manual_customer(command.username, command.place_id, now)
                    if identity is None
                    else create_customer(identity, command.place_id, now)
                )
            else:
                if identity is not None:
                    username_history = refresh_identity(customer, identity, now)
                    if username_history is not None:
                        await CustomerUsernameHistoryRepository(session).save(username_history)
                place_history = update_place_id(customer, command.place_id, now)
                if place_history is not None:
                    await CustomerPlaceIDHistoryRepository(session).save(place_history)
                await customers.save(customer)
            settings = await _get_or_create_settings(
                SystemSettingsRepository(session),
                self._settings_defaults,
                for_update=False,
            )
            orders = ClientOrderRepository(session)
            if not command.allow_duplicate:
                similar = await orders.find_similar_active(
                    username=command.username,
                    place_id=command.place_id,
                    requested_robux=command.requested_robux,
                )
                if similar is not None:
                    raise ConflictError(f"Similar active order {similar.id} already exists")
            order = await orders.save(
                create_draft(
                    customer,
                    command.requested_robux,
                    command.place_id,
                    settings.maximum_purchase_rate,
                )
            )
            await TimelineEventRepository(session).save(
                create_timeline_event(
                    order,
                    TimelineEventType.ORDER_CREATED,
                    "Client Order created as Draft.",
                    now,
                )
            )
            place_cache = UserPlaceCacheRepository(session)
            remembered = await place_cache.get_by_username_for_update(command.username)
            if remembered is None:
                remembered = UserPlaceCache(
                    roblox_username=command.username.casefold(),
                    place_id=command.place_id,
                    place_name=command.place_name,
                    last_used_at=now,
                )
            else:
                remembered.roblox_username = command.username.casefold()
                remembered.place_id = command.place_id
                remembered.place_name = command.place_name
                remembered.last_used_at = now
            await place_cache.save(remembered)
            return order

    async def edit_draft(self, command: EditDraftCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        try:
            async with self._sessions.begin() as session:
                repository = ClientOrderRepository(session)
                order = await repository.get_for_update(command.order_id)
                if order is None:
                    raise NotFoundError("Client Order")
                edit_draft(
                    order,
                    requested_robux=command.requested_robux,
                    place_id=command.place_id,
                )
                await repository.save(order)
        except (DomainValidationError, DomainConflictError) as error:
            _raise_domain_error(error)
        return ActionResultDTO(message="Draft order was updated.")

    async def delete_draft(self, command: OrderActionCommand) -> ActionResultDTO:
        """Logically delete a Draft using Cancelled because history cannot be deleted."""
        return await self._cancel(command, draft_only=True)

    async def confirm_payment(self, command: OrderActionCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        if self._marketplace_workflows is not None:
            return await self._marketplace_workflows.start_purchase(command.order_id)
        try:
            async with self._sessions.begin() as session:
                orders = ClientOrderRepository(session)
                order = await orders.get_for_update(command.order_id)
                if order is None:
                    raise NotFoundError("Client Order")
                if order.current_status is not ClientOrderStatus.DRAFT:
                    raise DomainConflictError("Payment can be confirmed only for a Draft order")
                stock_available = await self._marketplace.has_suitable_stock(
                    order.requested_robux,
                    order.marketplace_rate_limit,
                )
                timeline = TimelineEventRepository(session)
                event_time = self._clock()
                await timeline.save(
                    create_timeline_event(
                        order,
                        TimelineEventType.PAYMENT_CONFIRMED,
                        "Customer payment confirmed.",
                        event_time,
                    )
                )
                if not stock_available:
                    enter_preorder(order)
                    await orders.save(order)
                    await timeline.save(
                        create_timeline_event(
                            order,
                            TimelineEventType.PREORDER_CREATED,
                            "No suitable stock was available; order entered PreOrder.",
                            event_time + timedelta(microseconds=1),
                        )
                    )
                    result_message = "Payment confirmed; order is waiting in PreOrder."
                else:
                    start_purchasing(order)
                    external_result = await self._marketplace.create_order(
                        client_order_id=order.id,
                        place_id=order.current_place_id,
                        requested_robux=order.requested_robux,
                        maximum_rate=order.marketplace_rate_limit,
                    )
                    marketplace_orders = MarketplaceOrderRepository(session)
                    active = await marketplace_orders.get_active_for_client_order(order.id)
                    attempt = create_marketplace_order(
                        order,
                        external_result,
                        active_order_exists=active is not None,
                    )
                    await orders.save(order)
                    await marketplace_orders.save(attempt)
                    await timeline.save(
                        create_timeline_event(
                            order,
                            TimelineEventType.PURCHASING_STARTED,
                            "Suitable stock found; Purchasing started.",
                            event_time + timedelta(microseconds=1),
                        )
                    )
                    await timeline.save(
                        create_timeline_event(
                            order,
                            TimelineEventType.MARKETPLACE_ORDER_CREATED,
                            "Marketplace Order created.",
                            event_time + timedelta(microseconds=2),
                        )
                    )
                    result_message = "Payment confirmed; Purchasing started."
        except (DomainValidationError, DomainConflictError) as error:
            _raise_domain_error(error)
        except IntegrityError as error:
            raise ConflictError("The order changed concurrently; please refresh") from error
        return ActionResultDTO(message=result_message)

    async def start_purchase(self, command: OrderActionCommand) -> ActionResultDTO:
        """Start a waiting PreOrder through the concrete marketplace workflow."""
        _authorize(command.operator_id, self._operator_id)
        if self._marketplace_workflows is None:
            raise FeatureUnavailableError("Marketplace purchasing")
        return await self._marketplace_workflows.start_purchase(command.order_id)

    async def send_to_preorder(self, command: OrderActionCommand) -> ActionResultDTO:
        """Move an explicitly accepted Draft to the local PreOrder queue."""
        _authorize(command.operator_id, self._operator_id)
        try:
            async with self._sessions.begin() as session:
                orders = ClientOrderRepository(session)
                order = await orders.get_for_update(command.order_id)
                if order is None:
                    raise NotFoundError("Client Order")
                if order.current_status is ClientOrderStatus.PREORDER:
                    return ActionResultDTO(
                        message="PreOrder already exists.",
                        order_id=order.id,
                    )
                if order.current_status is not ClientOrderStatus.DRAFT:
                    raise DomainConflictError("Only a Draft can be sent to PreOrders")
                customer = await CustomerRepository(session).get(order.customer_id)
                if customer is None:
                    raise NotFoundError("Customer")
                now = self._clock()
                timeline = TimelineEventRepository(session)
                await timeline.save(
                    create_timeline_event(
                        order,
                        TimelineEventType.PAYMENT_CONFIRMED,
                        "Customer payment confirmed.",
                        now,
                    )
                )
                enter_preorder(order)
                await orders.save(order)
                await timeline.save(
                    create_timeline_event(
                        order,
                        TimelineEventType.PREORDER_CREATED,
                        "Operator accepted the local PreOrder fallback.",
                        now + timedelta(microseconds=1),
                    )
                )
                logger.info(
                    "preorder_created",
                    extra={
                        "order_id": str(order.id),
                        "customer": customer.current_username,
                        "requested_robux": order.requested_robux,
                        "place_id": order.current_place_id,
                    },
                )
        except (DomainValidationError, DomainConflictError) as error:
            _raise_domain_error(error)
        return ActionResultDTO(message="PreOrder created.", order_id=command.order_id)

    async def manual_reorder(self, command: OrderActionCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        if self._marketplace_workflows is None:
            raise FeatureUnavailableError("Manual reorder")
        return await self._marketplace_workflows.manual_requeue(command.order_id)

    async def toggle_auto_requeue(self, command: OrderActionCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        try:
            async with self._sessions.begin() as session:
                repository = ClientOrderRepository(session)
                order = await repository.get_for_update(command.order_id)
                if order is None:
                    raise NotFoundError("Client Order")
                if order.current_status is not ClientOrderStatus.PURCHASING:
                    raise DomainConflictError(
                        "Auto Requeue can be changed only for an active purchase"
                    )
                enabled = not (order.automatic_requeue_enabled is not False)
                order.automatic_requeue_enabled = enabled
                await repository.save(order)
        except (DomainValidationError, DomainConflictError) as error:
            _raise_domain_error(error)
        return ActionResultDTO(
            message=f"Auto Requeue {'enabled' if enabled else 'disabled'}.",
            order_id=command.order_id,
        )

    async def finalize_purchase(
        self,
        command: FinalizePurchaseCommand,
    ) -> ActionResultDTO:
        """Atomically apply a validated marketplace success report once."""
        try:
            async with self._sessions.begin() as session:
                orders = ClientOrderRepository(session)
                order = await orders.get_for_update(command.order_id)
                if order is None:
                    raise NotFoundError("Client Order")
                marketplace_orders = MarketplaceOrderRepository(session)
                attempt = await marketplace_orders.get_for_update(command.marketplace_order_id)
                if attempt is None or attempt.client_order_id != order.id:
                    raise NotFoundError("Marketplace Order")
                if order.current_status is ClientOrderStatus.COMPLETED:
                    if attempt.marketplace_status is MarketplaceOrderStatus.COMPLETED:
                        return ActionResultDTO(message="Order is already completed.")
                    raise DomainConflictError(
                        "Completed Client Order has an inconsistent Marketplace Order"
                    )
                settings = await _get_or_create_settings(
                    SystemSettingsRepository(session),
                    self._settings_defaults,
                    for_update=False,
                )
                customer_receives = calculate_customer_receives(
                    order.requested_robux,
                    tax_rate=command.roblox_tax_rate,
                    rounding=command.robux_rounding,
                )
                financials = calculate_financial_snapshot(
                    marketplace_cost=command.marketplace_cost,
                    commission_rate=settings.marketplace_commission,
                    usd_exchange_rate=settings.usd_exchange_rate,
                    money_quantum=command.money_quantum,
                    rounding=command.money_rounding,
                )
                now = self._clock()
                complete_marketplace_order(
                    attempt,
                    purchased_robux=command.purchased_robux,
                    now=now,
                )
                apply_order_completion(
                    order,
                    customer_receives=customer_receives,
                    marketplace_cost=financials.marketplace_cost,
                    marketplace_commission=financials.marketplace_commission,
                    final_cost_usd=financials.final_cost_usd,
                    final_cost_local_currency=financials.final_cost_local_currency,
                    usd_exchange_rate=financials.usd_exchange_rate,
                    now=now,
                )
                await marketplace_orders.save(attempt)
                await orders.save(order)
                timeline = TimelineEventRepository(session)
                await timeline.save(
                    create_timeline_event(
                        order,
                        TimelineEventType.MARKETPLACE_ORDER_COMPLETED,
                        "Marketplace confirmed successful execution.",
                        now,
                    )
                )
                await timeline.save(
                    create_timeline_event(
                        order,
                        TimelineEventType.ORDER_COMPLETED,
                        "Client Order completed with historical financial values.",
                        now + timedelta(microseconds=1),
                    )
                )
        except (DomainValidationError, DomainConflictError) as error:
            _raise_domain_error(error)
        return ActionResultDTO(message="Order was completed.")

    async def cancel_order(self, command: OrderActionCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        if self._marketplace_workflows is not None:
            return await self._marketplace_workflows.cancel_active_purchase(command.order_id)
        return await self._cancel(command, draft_only=False)

    async def _cancel(
        self,
        command: OrderActionCommand,
        *,
        draft_only: bool,
    ) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        try:
            async with self._sessions.begin() as session:
                orders = ClientOrderRepository(session)
                order = await orders.get_for_update(command.order_id)
                if order is None:
                    raise NotFoundError("Client Order")
                if order.current_status is ClientOrderStatus.CANCELLED:
                    return ActionResultDTO(message="Order is already cancelled.")
                if draft_only and order.current_status is not ClientOrderStatus.DRAFT:
                    raise DomainConflictError("Only a Draft order can be deleted")
                timeline = TimelineEventRepository(session)
                if order.current_status is ClientOrderStatus.PURCHASING:
                    marketplace_orders = MarketplaceOrderRepository(session)
                    active = await marketplace_orders.get_active_for_client_order_for_update(
                        order.id
                    )
                    if active is None:
                        raise DomainConflictError(
                            "Purchasing order has no active Marketplace Order"
                        )
                    confirmation = await self._marketplace.cancel_order(active.rbxcreate_order_id)
                    cancel_marketplace_order(
                        active,
                        purchased_robux=confirmation.purchased_robux,
                        remaining_robux=confirmation.remaining_robux,
                        now=self._clock(),
                    )
                    await marketplace_orders.save(active)
                    await timeline.save(
                        create_timeline_event(
                            order,
                            TimelineEventType.MARKETPLACE_ORDER_CANCELLED,
                            "Marketplace Order cancellation confirmed.",
                            self._clock(),
                        )
                    )
                apply_order_cancellation(order, self._clock())
                await orders.save(order)
                await timeline.save(
                    create_timeline_event(
                        order,
                        TimelineEventType.ORDER_CANCELLED,
                        "Draft deleted and retained as Cancelled."
                        if draft_only
                        else "Client Order cancelled by the operator.",
                        self._clock() + timedelta(microseconds=1),
                    )
                )
        except (DomainValidationError, DomainConflictError) as error:
            _raise_domain_error(error)
        return ActionResultDTO(
            message="Draft was deleted and retained in history."
            if draft_only
            else "Order was cancelled."
        )

    async def refresh_order(self, command: OrderActionCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        if self._marketplace_workflows is not None:
            return await self._marketplace_workflows.synchronize_active_purchase(command.order_id)
        raise FeatureUnavailableError("Marketplace Order refresh")


class CustomerApplicationService:
    """Coordinate Customer reads, refresh, Place ID history, and archiving."""

    def __init__(
        self,
        sessions: SessionFactory,
        *,
        roblox: RobloxGateway | None = None,
        operator_id: int | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._sessions = sessions
        self._roblox = roblox or UnavailableRobloxGateway()
        self._operator_id = operator_id
        self._clock = clock

    async def search_customers(
        self,
        query: SearchCustomersQuery,
    ) -> PageDTO[CustomerSummaryDTO]:
        async with self._sessions() as session:
            repository = CustomerRepository(session)
            total_items = await repository.count(query.search_term, archived=query.archived)
            page_number = _bounded_page(query.page, query.page_size, total_items)
            customers = await repository.search(
                query.search_term,
                archived=query.archived,
                offset=(page_number - 1) * query.page_size,
                limit=query.page_size,
            )
        return PageDTO(
            items=tuple(_customer_summary(customer) for customer in customers),
            page=page_number,
            page_size=query.page_size,
            total_items=total_items,
        )

    async def get_customer(self, query: GetCustomerQuery) -> CustomerDetailDTO:
        async with self._sessions() as session:
            customer = await CustomerRepository(session).get_details(query.customer_id)
            if customer is None:
                raise NotFoundError("Customer")
            return _customer_detail(customer)

    async def refresh_customer(self, command: CustomerActionCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        try:
            async with self._sessions.begin() as session:
                customers = CustomerRepository(session)
                customer = await customers.get_for_update(command.customer_id)
                if customer is None:
                    raise NotFoundError("Customer")
                if customer.roblox_user_id is None:
                    identity = await self._roblox.resolve_username(customer.current_username)
                else:
                    identity = await self._roblox.refresh_identity(customer.roblox_user_id)
                discovered_place_id = await self._roblox.discover_place_id(identity.user_id)
                now = self._clock()
                username_history = refresh_identity(customer, identity, now)
                place_history = (
                    None
                    if discovered_place_id is None
                    else update_place_id(customer, discovered_place_id, now)
                )
                if username_history is not None:
                    await CustomerUsernameHistoryRepository(session).save(username_history)
                if place_history is not None:
                    await CustomerPlaceIDHistoryRepository(session).save(place_history)
                await customers.save(customer)
        except (DomainValidationError, DomainConflictError) as error:
            _raise_domain_error(error)
        return ActionResultDTO(
            message="Customer information was refreshed."
            if username_history is not None or place_history is not None
            else "Customer information is already current."
        )

    async def update_place_id(self, command: UpdatePlaceIDCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        try:
            async with self._sessions.begin() as session:
                customers = CustomerRepository(session)
                customer = await customers.get_for_update(command.customer_id)
                if customer is None:
                    raise NotFoundError("Customer")
                history = update_place_id(customer, command.place_id, self._clock())
                if history is not None:
                    await CustomerPlaceIDHistoryRepository(session).save(history)
                await customers.save(customer)
        except (DomainValidationError, DomainConflictError) as error:
            _raise_domain_error(error)
        return ActionResultDTO(
            message="Place ID was updated."
            if history is not None
            else "Place ID is already current."
        )

    async def archive_customer(self, command: ArchiveCustomerCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        async with self._sessions.begin() as session:
            customers = CustomerRepository(session)
            customer = await customers.get_for_update(command.customer_id)
            if customer is None:
                raise NotFoundError("Customer")
            changed = apply_customer_archive(customer, command.archived, self._clock())
            await customers.save(customer)
        return ActionResultDTO(
            message="Customer was archived." if changed else "Customer is already archived."
        )


class SettingsApplicationService:
    """Initialize, validate, and persist the singleton System Settings."""

    def __init__(
        self,
        sessions: SessionFactory,
        *,
        defaults: SettingsDefaults | None = None,
        operator_id: int | None = None,
    ) -> None:
        self._sessions = sessions
        self._defaults = defaults
        self._operator_id = operator_id

    async def get_settings(self) -> SettingsDTO | None:
        if self._defaults is None:
            async with self._sessions() as session:
                settings = await SystemSettingsRepository(session).get_current()
        else:
            async with self._sessions.begin() as session:
                settings = await _get_or_create_settings(
                    SystemSettingsRepository(session),
                    self._defaults,
                    for_update=False,
                )
        return None if settings is None else _settings(settings)

    async def update_setting(self, command: UpdateSettingCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        try:
            async with self._sessions.begin() as session:
                repository = SystemSettingsRepository(session)
                settings = await _get_or_create_settings(
                    repository,
                    self._defaults,
                    for_update=True,
                )
                value = apply_setting_update(settings, command.field, command.value)
                await repository.save(settings)
        except (DomainValidationError, DomainConflictError) as error:
            _raise_domain_error(error)
        except IntegrityError as error:
            raise ConflictError("System Settings changed concurrently; please retry") from error
        rendered = (
            ", ".join(item.value for item in value) if isinstance(value, list) else str(value)
        )
        return ActionResultDTO(message=f"{command.field.value} was updated to {rendered}.")


class StatisticsApplicationService:
    """Read persisted Statistics without calculating them in this milestone."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def get_statistics(self, query: GetStatisticsQuery) -> StatisticsDTO | None:
        async with self._sessions() as session:
            statistics = await StatisticsRepository(session).get_latest(query.period)
            return None if statistics is None else _statistics(statistics)


class SystemApplicationService:
    """Report safe runtime availability without exposing infrastructure details."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        sessions: SessionFactory | None = None,
        rbxcrate: RbxcreateBridge | None = None,
        automation: AutomationLoop | None = None,
        recovery: RecoveryService | None = None,
        operator_id: int | None = None,
    ) -> None:
        self._engine = engine
        self._sessions = sessions
        self._rbxcrate = rbxcrate
        self._automation = automation
        self._recovery = recovery
        self._operator_id = operator_id

    async def get_status(self) -> SystemStatusDTO:
        try:
            await verify_database_connection(self._engine)
        except SQLAlchemyError:
            database_available = False
        else:
            database_available = True

        active_marketplace_orders: int | None = None
        pending_preorders: int | None = None
        if database_available and self._sessions is not None:
            try:
                async with self._sessions() as session:
                    active_marketplace_orders = await MarketplaceOrderRepository(
                        session
                    ).count_by_status(MarketplaceOrderStatus.ACTIVE)
                    pending_preorders = await ClientOrderRepository(session).count_by_status(
                        ClientOrderStatus.PREORDER
                    )
            except SQLAlchemyError:
                database_available = False

        rbxcrate_balance: Decimal | None = None
        if self._rbxcrate is None:
            marketplace_available = None
        else:
            try:
                balance = await self._rbxcrate.get_balance()
            except MarketplaceIntegrationError:
                marketplace_available = False
            else:
                marketplace_available = True
                rbxcrate_balance = balance.quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
        return SystemStatusDTO(
            application_available=True,
            database_available=database_available,
            telegram_available=True,
            marketplace_available=marketplace_available,
            automation_available=(
                None if self._automation is None else self._automation.is_running
            ),
            rbxcrate_balance=rbxcrate_balance,
            active_marketplace_orders=active_marketplace_orders,
            pending_preorders=pending_preorders,
        )

    async def run_recovery_now(self, command: SystemActionCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        if self._recovery is None:
            raise FeatureUnavailableError("Recovery")
        result = await self._recovery.recover_incomplete_orders()
        return ActionResultDTO(
            message=(f"Recovery checked {result.checked} orders and repaired {result.repaired}.")
        )

    async def run_sync_pass_now(self, command: SystemActionCommand) -> ActionResultDTO:
        _authorize(command.operator_id, self._operator_id)
        if self._automation is None:
            raise FeatureUnavailableError("Marketplace synchronization")
        processed = await self._automation.run_synchronization_pass()
        return ActionResultDTO(
            message=f"Synchronization processed {processed} active Marketplace Orders."
        )
