"""Small pagination helpers shared by Telegram list screens."""

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True, slots=True)
class Pagination:
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, ceil(self.total_items / self.page_size))

    @property
    def previous_page(self) -> int | None:
        return self.page - 1 if self.page > 1 else None

    @property
    def next_page(self) -> int | None:
        return self.page + 1 if self.page < self.total_pages else None
