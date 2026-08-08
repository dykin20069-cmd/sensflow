"""Reusable low-level async HTTP client for RBXCrate."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from time import perf_counter

import httpx
from pydantic import SecretStr

from sensflow.integrations.rbxcreate.errors import (
    RbxcrateApiError,
    RbxcrateAuthenticationError,
    RbxcrateDailyLimitReachedError,
    RbxcrateDuplicateOrderError,
    RbxcrateError,
    RbxcrateInsufficientFundsError,
    RbxcrateInsufficientStockError,
    RbxcrateOrderNotFoundError,
    RbxcrateUnsupportedStatusError,
    RbxcrateValidationError,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=30.0)
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (0.5, 1.0, 2.0)
RetrySleep = Callable[[float], Awaitable[None]]

ERROR_TYPES: dict[int, type[RbxcrateError]] = {
    400: RbxcrateValidationError,
    401: RbxcrateAuthenticationError,
    402: RbxcrateInsufficientStockError,
    403: RbxcrateInsufficientFundsError,
    404: RbxcrateOrderNotFoundError,
    409: RbxcrateDuplicateOrderError,
    422: RbxcrateUnsupportedStatusError,
    429: RbxcrateDailyLimitReachedError,
}


class RbxcrateClient:
    """Own one reusable ``httpx.AsyncClient`` and transport retry policy."""

    def __init__(
        self,
        *,
        api_key: SecretStr | str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: RetrySleep = asyncio.sleep,
    ) -> None:
        secret = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"api-key": secret, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            transport=transport,
        )
        self._sleep = sleep

    async def get(self, path: str) -> httpx.Response:
        """Perform one authenticated GET request with the shared retry policy."""
        return await self._request("GET", path)

    async def post(
        self,
        path: str,
        json_body: Mapping[str, object],
    ) -> httpx.Response:
        """Perform one authenticated JSON POST with the shared retry policy."""
        return await self._request("POST", path, json_body=json_body)

    async def aclose(self) -> None:
        """Close the owned connection pool."""
        await self._client.aclose()

    async def __aenter__(self) -> "RbxcrateClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, object] | None = None,
    ) -> httpx.Response:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            started_at = perf_counter()
            try:
                response = await self._client.request(method, path, json=json_body)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as error:
                self._log_attempt(method, path, attempt, None, started_at)
                if attempt == MAX_ATTEMPTS:
                    raise RbxcrateApiError(
                        f"RBXCrate request failed after {MAX_ATTEMPTS} attempts: "
                        f"{type(error).__name__}",
                        path=path,
                    ) from error
                await self._sleep(RETRY_BACKOFF_SECONDS[attempt - 1])
                continue
            except httpx.HTTPError as error:
                self._log_attempt(method, path, attempt, None, started_at)
                raise RbxcrateApiError(
                    f"RBXCrate request failed: {type(error).__name__}",
                    path=path,
                ) from error

            self._log_attempt(method, path, attempt, response.status_code, started_at)
            if response.status_code >= 500:
                if attempt < MAX_ATTEMPTS:
                    await self._sleep(RETRY_BACKOFF_SECONDS[attempt - 1])
                    continue
                self._raise_response_error(response, path)
            if response.status_code >= 400:
                self._raise_response_error(response, path)
            return response
        raise AssertionError("unreachable retry state")

    @staticmethod
    def _log_attempt(
        method: str,
        path: str,
        attempt: int,
        status_code: int | None,
        started_at: float,
    ) -> None:
        duration_ms = (perf_counter() - started_at) * 1000
        logger.info(
            "rbxcrate_request method=%s path=%s attempt=%d status_code=%s duration_ms=%.2f",
            method,
            path,
            attempt,
            status_code,
            duration_ms,
        )

    @staticmethod
    def _raise_response_error(response: httpx.Response, request_path: str) -> None:
        message, path, timestamp = _error_details(response, request_path)
        error_type = ERROR_TYPES.get(response.status_code, RbxcrateApiError)
        raise error_type(
            message,
            status_code=response.status_code,
            path=path,
            timestamp=timestamp,
            response_text=response.text,
        )


def _error_details(response: httpx.Response, request_path: str) -> tuple[str, str, str | None]:
    message: object = None
    path: object = None
    timestamp: object = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message")
        path = payload.get("path")
        timestamp = payload.get("timestamp")
    if isinstance(message, list):
        message = "; ".join(str(item) for item in message)
    safe_message = (
        message if isinstance(message, str) and message else "RBXCrate API request failed"
    )
    safe_path = path if isinstance(path, str) and path else request_path
    safe_timestamp = timestamp if isinstance(timestamp, str) and timestamp else None
    details = f"{safe_message} (path={safe_path}"
    if safe_timestamp is not None:
        details += f", timestamp={safe_timestamp}"
    details += f", status={response.status_code})"
    return details, safe_path, safe_timestamp
