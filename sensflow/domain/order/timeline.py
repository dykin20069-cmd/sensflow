"""Creation of immutable Client Order timeline records."""

from datetime import datetime

from sensflow.domain.enums import TimelineEventType
from sensflow.domain.errors import DomainValidationError
from sensflow.infrastructure.database.models import ClientOrder, TimelineEvent


def create_timeline_event(
    order: ClientOrder,
    event_type: TimelineEventType,
    description: str,
    created_at: datetime,
) -> TimelineEvent:
    """Build one append-only event tied to an already-persisted Client Order."""
    normalized = description.strip()
    if not normalized:
        raise DomainValidationError("Timeline description must not be empty")
    return TimelineEvent(
        client_order_id=order.id,
        event_type=event_type,
        description=normalized,
        created_at=created_at,
    )
