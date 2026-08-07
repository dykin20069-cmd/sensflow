"""Statistics repository."""

from datetime import date

from sqlalchemy import select

from sensflow.domain.enums import StatisticsPeriod
from sensflow.infrastructure.database.models import Statistics
from sensflow.repositories.base import Repository


class StatisticsRepository(Repository[Statistics]):
    """Persist and retrieve period-based statistics projections."""

    model = Statistics

    async def get_for_period(
        self,
        period: StatisticsPeriod,
        period_start: date,
    ) -> Statistics | None:
        statement = select(Statistics).where(
            Statistics.period == period,
            Statistics.period_start == period_start,
        )
        return await self.session.scalar(statement)

    async def get_latest(self, period: StatisticsPeriod) -> Statistics | None:
        statement = (
            select(Statistics)
            .where(Statistics.period == period)
            .order_by(Statistics.period_start.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def list_by_period(
        self,
        period: StatisticsPeriod,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Statistics]:
        statement = (
            select(Statistics)
            .where(Statistics.period == period)
            .order_by(Statistics.period_start.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)
