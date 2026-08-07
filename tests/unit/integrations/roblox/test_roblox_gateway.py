"""Official Roblox username and public-place resolver tests."""

import asyncio
from decimal import Decimal

import httpx

from sensflow.integrations.roblox import RobloxPlaceResolver


def test_resolver_returns_verified_identity_and_public_places() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "users.roblox.com":
                assert request.method == "POST"
                return httpx.Response(
                    200,
                    json={"data": [{"id": 42, "name": "Builderman"}]},
                )
            assert request.url.host == "games.roblox.com"
            assert request.url.params["accessFilter"] == "Public"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 9002,
                            "name": "Small Place",
                            "rootPlace": {"id": 102},
                            "placeVisits": 20,
                            "updated": "2026-08-07T10:00:00Z",
                        },
                        {
                            "id": 9001,
                            "name": "Popular Place",
                            "rootPlace": {"id": 101},
                            "placeVisits": 1_200_000,
                            "updated": "2026-08-07T11:00:00Z",
                        },
                    ],
                    "nextPageCursor": None,
                },
            )

        resolver = RobloxPlaceResolver(transport=httpx.MockTransport(handler))
        try:
            resolution = await resolver.resolve_public_places("builderman")
        finally:
            await resolver.aclose()

        assert resolution.identity.user_id == 42
        assert resolution.identity.username == "Builderman"
        assert [place.place_id for place in resolution.places] == [101, 102]
        assert resolution.places[0].universe_id == 9001
        assert resolution.places[0].place_name == "Popular Place"
        assert resolution.places[0].visits == 1_200_000
        assert resolution.places[0].updated_at.tzinfo is not None

    asyncio.run(scenario())


def test_resolver_retries_transient_failure_without_decimal_or_falsy_assumptions() -> None:
    async def scenario() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, json={})
            return httpx.Response(200, json={"data": [{"id": 7, "name": "ValidUser"}]})

        resolver = RobloxPlaceResolver(
            transport=httpx.MockTransport(handler),
            sleep=lambda _: asyncio.sleep(0),
        )
        try:
            identity = await resolver.resolve_username("ValidUser")
        finally:
            await resolver.aclose()

        assert calls == 2
        assert identity.user_id == 7
        assert Decimal(identity.user_id) == Decimal("7")

    asyncio.run(scenario())
