"""Production adapter for official public Roblox identity and games APIs."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx
from pydantic import ValidationError

from sensflow.application.errors import NotFoundError, RobloxIntegrationError
from sensflow.application.gateways import RobloxPlaceResolution, RobloxPublicPlace
from sensflow.domain.customer.service import RobloxIdentity
from sensflow.integrations.roblox.models import (
    PublicGamesResponse,
    RobloxUser,
    UsernameLookupResponse,
)

USERS_BASE_URL = "https://users.roblox.com"
GAMES_BASE_URL = "https://games.roblox.com"
REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=15.0)
RETRY_DELAYS = (0.25, 0.5)
MAX_GAME_PAGES = 10
RetrySleep = Callable[[float], Awaitable[None]]


class RobloxPlaceResolver:
    """Resolve a username and enumerate public root places owned by that user."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: RetrySleep = asyncio.sleep,
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            transport=transport,
            headers={"Accept": "application/json"},
        )
        self._sleep = sleep

    async def resolve_username(self, username: str) -> RobloxIdentity:
        response = await self._request(
            "POST",
            f"{USERS_BASE_URL}/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": True},
        )
        try:
            payload = UsernameLookupResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise RobloxIntegrationError("Roblox returned an invalid identity response") from error
        if not payload.data:
            raise NotFoundError("Roblox user")
        user = payload.data[0]
        return RobloxIdentity(user.id, user.name)

    async def refresh_identity(self, roblox_user_id: int) -> RobloxIdentity:
        response = await self._request(
            "GET",
            f"{USERS_BASE_URL}/v1/users/{roblox_user_id}",
        )
        try:
            user = RobloxUser.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise RobloxIntegrationError("Roblox returned an invalid identity response") from error
        return RobloxIdentity(user.id, user.name)

    async def discover_place_id(self, roblox_user_id: int) -> int | None:
        places = await self._get_public_places(roblox_user_id)
        return None if not places else places[0].place_id

    async def resolve_public_places(self, username: str) -> RobloxPlaceResolution:
        identity = await self.resolve_username(username)
        places = await self._get_public_places(identity.user_id)
        return RobloxPlaceResolution(identity=identity, places=places)

    async def aclose(self) -> None:
        """Close the reusable HTTP connection pool."""
        await self._client.aclose()

    async def _get_public_places(self, roblox_user_id: int) -> tuple[RobloxPublicPlace, ...]:
        cursor: str | None = None
        places: list[RobloxPublicPlace] = []
        for _ in range(MAX_GAME_PAGES):
            params: dict[str, object] = {
                "accessFilter": "Public",
                "limit": 50,
                "sortOrder": "Asc",
            }
            if cursor is not None:
                params["cursor"] = cursor
            response = await self._request(
                "GET",
                f"{GAMES_BASE_URL}/v2/users/{roblox_user_id}/games",
                params=params,
            )
            try:
                payload = PublicGamesResponse.model_validate(response.json())
            except (ValueError, ValidationError) as error:
                raise RobloxIntegrationError(
                    "Roblox returned an invalid public places response"
                ) from error
            places.extend(
                RobloxPublicPlace(
                    place_id=item.root_place.id,
                    universe_id=item.universe_id,
                    place_name=item.name,
                    visits=item.visits,
                    updated_at=item.updated_at,
                )
                for item in payload.data
            )
            cursor = payload.next_page_cursor
            if cursor is None:
                break
        return tuple(sorted(places, key=lambda item: (-item.visits, item.place_id)))

    async def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = await self._client.request(method, url, **kwargs)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as error:
                if attempt == len(RETRY_DELAYS):
                    raise RobloxIntegrationError("Roblox API is temporarily unavailable") from error
                await self._sleep(RETRY_DELAYS[attempt])
                continue
            except httpx.HTTPError as error:
                raise RobloxIntegrationError("Roblox API request failed") from error
            if response.status_code == 404:
                raise NotFoundError("Roblox resource")
            if (response.status_code == 429 or response.status_code >= 500) and attempt < len(
                RETRY_DELAYS
            ):
                await self._sleep(RETRY_DELAYS[attempt])
                continue
            if response.status_code >= 400:
                raise RobloxIntegrationError(
                    f"Roblox API rejected the request with status {response.status_code}"
                )
            return response
        raise AssertionError("unreachable Roblox retry state")
