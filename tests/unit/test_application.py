"""Tests for application composition and lifecycle."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sensflow.application.lifecycle import Application
from sensflow.infrastructure.config import load_settings


def application_dependencies() -> tuple[MagicMock, MagicMock, MagicMock]:
    engine = MagicMock()
    engine.dispose = AsyncMock()
    bot = MagicMock()
    bot.session.close = AsyncMock()
    dispatcher = MagicMock()
    dispatcher.start_polling = AsyncMock()
    dispatcher.stop_polling = AsyncMock()
    return engine, bot, dispatcher


@pytest.mark.unit
def test_application_starts_and_stops(valid_environment: dict[str, str]) -> None:
    async def exercise_lifecycle() -> None:
        engine, bot, dispatcher = application_dependencies()
        external_resource = MagicMock()
        external_resource.aclose = AsyncMock()
        application = Application(
            load_settings(valid_environment),
            engine,
            bot,
            dispatcher,
            external_resources=(external_resource,),
        )

        with patch(
            "sensflow.application.lifecycle.verify_database_connection",
            new=AsyncMock(),
        ) as verify_connection:
            await application.start()
            await asyncio.sleep(0)
            await application.stop()

        verify_connection.assert_awaited_once_with(engine)
        dispatcher.start_polling.assert_awaited_once_with(
            bot,
            handle_signals=False,
            close_bot_session=False,
        )
        bot.session.close.assert_awaited_once()
        engine.dispose.assert_awaited_once()
        external_resource.aclose.assert_awaited_once()

    asyncio.run(exercise_lifecycle())


@pytest.mark.unit
def test_application_run_honors_shutdown_request(valid_environment: dict[str, str]) -> None:
    async def exercise_run() -> None:
        engine, bot, dispatcher = application_dependencies()
        polling_stopped = asyncio.Event()

        async def poll(*args: object, **kwargs: object) -> None:
            await polling_stopped.wait()

        async def stop_polling() -> None:
            polling_stopped.set()

        dispatcher.start_polling.side_effect = poll
        dispatcher.stop_polling.side_effect = stop_polling
        application = Application(load_settings(valid_environment), engine, bot, dispatcher)

        with patch(
            "sensflow.application.lifecycle.verify_database_connection",
            new=AsyncMock(),
        ):
            run_task = asyncio.create_task(application.run())

            await asyncio.sleep(0)
            application.request_shutdown("test")
            await asyncio.wait_for(run_task, timeout=1)

        dispatcher.stop_polling.assert_awaited_once()
        bot.session.close.assert_awaited_once()
        engine.dispose.assert_awaited_once()

    asyncio.run(exercise_run())


@pytest.mark.unit
def test_bootstrap_constructs_the_rbxcrate_gateway(valid_environment: dict[str, str]) -> None:
    from sensflow.bootstrap import create_application

    settings = load_settings(valid_environment)
    engine = MagicMock()
    sessions = MagicMock()
    bot = MagicMock()
    dispatcher = MagicMock()
    rbxcrate = MagicMock()

    with (
        patch("sensflow.bootstrap.create_database_engine", return_value=engine),
        patch("sensflow.bootstrap.create_session_factory", return_value=sessions),
        patch("sensflow.bootstrap.create_bot", return_value=bot),
        patch("sensflow.bootstrap.create_dispatcher", return_value=dispatcher),
        patch("sensflow.bootstrap.RbxcrateGateway", return_value=rbxcrate) as gateway_type,
    ):
        application = create_application(settings)

    gateway_type.assert_called_once_with(
        api_key=settings.rbxcrate.api_key,
        base_url=settings.rbxcrate.base_url,
    )
    assert application.external_resources == (rbxcrate,)


@pytest.mark.unit
def test_bootstrap_uses_isolated_rbxcrate_dry_run_gateway(
    valid_environment: dict[str, str],
) -> None:
    from sensflow.bootstrap import create_application

    valid_environment["RBXCRATE_DRY_RUN"] = "true"
    settings = load_settings(valid_environment)
    engine = MagicMock()
    sessions = MagicMock()
    bot = MagicMock()
    dispatcher = MagicMock()
    dry_run_gateway = MagicMock()

    with (
        patch("sensflow.bootstrap.create_database_engine", return_value=engine),
        patch("sensflow.bootstrap.create_session_factory", return_value=sessions),
        patch("sensflow.bootstrap.create_bot", return_value=bot),
        patch("sensflow.bootstrap.create_dispatcher", return_value=dispatcher),
        patch(
            "sensflow.bootstrap.RbxcrateDryRunGateway",
            return_value=dry_run_gateway,
        ) as dry_run_type,
        patch("sensflow.bootstrap.RbxcrateGateway") as live_gateway_type,
    ):
        application = create_application(settings)

    dry_run_type.assert_called_once_with()
    live_gateway_type.assert_not_called()
    assert application.external_resources == (dry_run_gateway,)
