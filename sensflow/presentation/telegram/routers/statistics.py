"""Persisted Statistics screen handlers."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

from sensflow.application.ports import StatisticsUseCases
from sensflow.application.queries import GetStatisticsQuery
from sensflow.domain.enums import StatisticsPeriod
from sensflow.presentation.telegram.callbacks import (
    MainSection,
    MenuCallback,
    NavigationAction,
    NavigationCallback,
    NavigationTarget,
    StatisticsCallback,
)
from sensflow.presentation.telegram.rendering import render_statistics, show_screen

router = Router(name="statistics")


async def _show_statistics(
    callback: CallbackQuery,
    statistics: StatisticsUseCases,
    period: StatisticsPeriod,
) -> None:
    projection = await statistics.get_statistics(GetStatisticsQuery(period=period))
    await show_screen(callback, render_statistics(projection, period))


@router.callback_query(MenuCallback.filter(F.section == MainSection.STATISTICS))
@router.callback_query(
    NavigationCallback.filter(
        (F.target == NavigationTarget.STATISTICS)
        & ((F.action == NavigationAction.BACK) | (F.action == NavigationAction.REFRESH))
    )
)
async def show_default_statistics(
    callback: CallbackQuery,
    statistics: StatisticsUseCases,
) -> None:
    await callback.answer()
    await _show_statistics(callback, statistics, StatisticsPeriod.DAILY)


@router.callback_query(StatisticsCallback.filter())
async def show_statistics_period(
    callback: CallbackQuery,
    callback_data: StatisticsCallback,
    statistics: StatisticsUseCases,
) -> None:
    await callback.answer()
    await _show_statistics(callback, statistics, callback_data.period)
