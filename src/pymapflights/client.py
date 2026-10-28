"""Asynchronous client for the map.flights API."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, ContentTypeError
from yarl import URL

from .const import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    HEADER_API_KEY,
    HEADER_ATTRIBUTION,
    HEADER_RATE_LIMIT,
    HEADER_RATE_REMAINING,
    HEADER_RATE_RESET,
    HEADER_RETRY_AFTER,
    NEAR_MAX_LIMIT,
    NEAR_MAX_RADIUS_KM,
)
from .exceptions import (
    MapFlightsAuthError,
    MapFlightsConnectionError,
    MapFlightsError,
    MapFlightsKeyDormantError,
    MapFlightsNotFoundError,
    MapFlightsNotInTariffError,
    MapFlightsOutOfAreaError,
    MapFlightsRateLimitError,
    MapFlightsTariffError,
)
from .models import NearResponse, RateLimitInfo

_NOT_IN_TARIFF = frozenset(
    {"group_not_in_tariff", "endpoint_not_in_tariff", "format_not_in_tariff"}
)


def _int_or_none(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _coord(value: float) -> str:
    """Format a path coordinate; 5 decimals are about 1 m."""
    return str(round(value, 5))


class MapFlights:
    """Client for the map.flights API.

    The aiohttp session is owned by the caller and never closed here.
    """

    def __init__(
        self,
        api_key: str,
        *,
        session: ClientSession,
        user_agent: str = DEFAULT_USER_AGENT,
        base_url: str = DEFAULT_BASE_URL,
        request_timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the client."""
        self._api_key = api_key
        self._session = session
        self._user_agent = user_agent
        self._base_url = URL(base_url)
        self._request_timeout = request_timeout
        self.attribution: str | None = None
        """Full attribution from the last `x-data-attribution` header."""
        self.rate_limit: RateLimitInfo | None = None
        """Rate-limit headers of the last response that carried them."""

    async def near(
        self,
        lat: float,
        lon: float,
        radius_km: float,
        *,
        limit: int | None = None,
    ) -> NearResponse:
        """Aircraft within `radius_km` of a point, nearest first.

        `limit` caps the returned list (API default 50); `total` of the
        response is the real number of aircraft in the radius.
        """
        if not -90 <= lat <= 90:  # noqa: PLR2004
            raise ValueError("lat must be between -90 and 90")
        if not -180 <= lon <= 180:  # noqa: PLR2004
            raise ValueError("lon must be between -180 and 180")
        if not 0 < radius_km <= NEAR_MAX_RADIUS_KM:
            raise ValueError(f"radius_km must be > 0 and <= {NEAR_MAX_RADIUS_KM}")
        params: dict[str, str] = {}
        if limit is not None:
            if not 1 <= limit <= NEAR_MAX_LIMIT:
                raise ValueError(f"limit must be between 1 and {NEAR_MAX_LIMIT}")
            params["limit"] = str(limit)

        data = await self._request(
            f"/api/v1/near/{_coord(lat)}/{_coord(lon)}/{_coord(radius_km)}",
            params=params,
        )
        return NearResponse.from_dict(data)

    async def _request(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        url = self._base_url.with_path(path)
        headers = {
            HEADER_API_KEY: self._api_key,
            "User-Agent": self._user_agent,
            "Accept": "application/json",
        }
        try:
            async with asyncio.timeout(self._request_timeout):
                response = await self._session.get(url, params=params, headers=headers)
                async with response:
                    self._read_headers(response)
                    body = await self._json(response)
        except TimeoutError as err:
            raise MapFlightsConnectionError(
                "Timeout while talking to map.flights"
            ) from err
        except ClientError as err:
            raise MapFlightsConnectionError(
                f"Error while talking to map.flights: {err}"
            ) from err

        if response.status >= 400:  # noqa: PLR2004
            raise self._error(response, body)
        if not isinstance(body, dict):
            raise MapFlightsError("Unexpected response from map.flights")
        return body

    def _read_headers(self, response: ClientResponse) -> None:
        if attribution := response.headers.get(HEADER_ATTRIBUTION):
            self.attribution = attribution
        if HEADER_RATE_REMAINING in response.headers:
            self.rate_limit = RateLimitInfo(
                limit=_int_or_none(response.headers.get(HEADER_RATE_LIMIT)),
                remaining=_int_or_none(response.headers.get(HEADER_RATE_REMAINING)),
                reset_s=_int_or_none(response.headers.get(HEADER_RATE_RESET)),
            )

    @staticmethod
    async def _json(response: ClientResponse) -> object:
        try:
            return await response.json()
        except (ContentTypeError, ValueError):
            if response.status < 400:  # noqa: PLR2004
                raise MapFlightsError("map.flights did not answer with JSON") from None
            return None

    @staticmethod
    def _error(  # noqa: PLR0911
        response: ClientResponse, body: object
    ) -> MapFlightsError:
        info: dict[str, Any] = body if isinstance(body, dict) else {}
        code = info.get("code")
        message = str(
            info.get("message") or info.get("error") or f"HTTP {response.status}"
        )

        if response.status == 401:  # noqa: PLR2004
            return MapFlightsAuthError(message)
        if response.status == 403:  # noqa: PLR2004
            tariff = info.get("tariff")
            code = str(code or "forbidden")
            if code == "out_of_area":
                return MapFlightsOutOfAreaError(message, code=code, tariff=tariff)
            if code == "key_dormant":
                return MapFlightsKeyDormantError(message, code=code, tariff=tariff)
            if code in _NOT_IN_TARIFF:
                return MapFlightsNotInTariffError(message, code=code, tariff=tariff)
            return MapFlightsTariffError(message, code=code, tariff=tariff)
        if response.status == 404:  # noqa: PLR2004
            return MapFlightsNotFoundError(message)
        if response.status == 429:  # noqa: PLR2004
            retry_after = _int_or_none(response.headers.get(HEADER_RETRY_AFTER))
            if retry_after is None:
                retry_after = _int_or_none(info.get("retryAfterS"))
            return MapFlightsRateLimitError(
                message,
                retry_after=retry_after,
                scope=info.get("scope"),
                limit=_int_or_none(info.get("limit")),
            )
        return MapFlightsError(f"HTTP {response.status}: {message}")
