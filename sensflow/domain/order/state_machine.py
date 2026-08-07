"""The canonical Version 1 ClientOrder state machine."""

from sensflow.domain.enums import ClientOrderStatus
from sensflow.domain.errors import DomainConflictError

ALLOWED_TRANSITIONS: dict[ClientOrderStatus, frozenset[ClientOrderStatus]] = {
    ClientOrderStatus.DRAFT: frozenset(
        {
            ClientOrderStatus.PREORDER,
            ClientOrderStatus.PURCHASING,
            ClientOrderStatus.CANCELLED,
        }
    ),
    ClientOrderStatus.PREORDER: frozenset(
        {ClientOrderStatus.PURCHASING, ClientOrderStatus.CANCELLED}
    ),
    ClientOrderStatus.PURCHASING: frozenset(
        {
            ClientOrderStatus.PREORDER,
            ClientOrderStatus.COMPLETED,
            ClientOrderStatus.CANCELLED,
        }
    ),
    ClientOrderStatus.COMPLETED: frozenset(),
    ClientOrderStatus.CANCELLED: frozenset(),
}


def validate_transition(
    current: ClientOrderStatus,
    target: ClientOrderStatus,
) -> None:
    """Reject every transition not explicitly required by the V1 lifecycle."""
    if target not in ALLOWED_TRANSITIONS[current]:
        raise DomainConflictError(f"Cannot transition an order from {current} to {target}")
