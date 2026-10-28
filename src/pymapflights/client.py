"""Asynchronous client for the map.flights API."""

from __future__ import annotations

import asyncio
import re
from contextlib import AbstractAsyncContextManager, nullcontext
from typing import Any, Literal

from aiohttp import ClientError, ClientResponse, ClientSession, ContentTypeError
from yarl import URL

from .const import (
    AIRCRAFT_FLIGHTS_MAX_LIMIT,
    AIRLINES_MAX_LIMIT,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    HEADER_API_KEY,
    HEADER_ATTRIBUTION,
    HEADER_RATE_LIMIT,
    HEADER_RATE_REMAINING,
    HEADER_RATE_RESET,
    HEADER_RETRY_AFTER,
    KEY_PREFIX_LENGTH,
    NEAR_MAX_LIMIT,
    NEAR_MAX_RADIUS_KM,
)
from .exceptions import (
    MapFlightsAuthError,
    MapFlightsConnectionError,
    MapFlightsError,
    MapFlightsKeyDormantError,
    MapFlightsNoCurrentFlightError,
    MapFlightsNotFoundError,
    MapFlightsNotInTariffError,
    MapFlightsOutOfAreaError,
    MapFlightsRateLimitError,
    MapFlightsTariffError,
)
from .models import (
    AircraftFlights,
    AirlinePage,
    DayBoard,
    FlightPage,
    Me,
    NearResponse,
    RateLimitInfo,
)
from .throttle import SCOPE_LIVE, SCOPE_MINUTE, throttle_for

_NOT_IN_TARIFF = frozenset(
    {"group_not_in_tariff", "endpoint_not_in_tariff", "format_not_in_tariff"}
)
_NO_CURRENT_FLIGHT = frozenset({"no current flight", "unknown flight"})

_AIRPORT_RE = re.compile(r"^[A-Za-z0-9-]{3,8}$")
_CALLSIGN_RE = re.compile(r"^[A-Za-z0-9-]{2,10}$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]{6}$")


def key_prefix(api_key: str) -> str:
    """Non-secret prefix of a key (`mf_live_` + 8 hex), as `/me` reports it.

    Unique per key and safe to log or use as an identifier. A new key of the
    same account has a different prefix.
    """
    api_key = api_key.strip()
    if len(api_key) < KEY_PREFIX_LENGTH:
        raise ValueError("API key is too short")
    return api_key[:KEY_PREFIX_LENGTH]


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

    The aiohttp session is owned by the caller and never closed here. Rate
    limits are enforced per key across all clients of the process: live
    requests (`near`) wait for their 5 s slot, and requests that would break
    the minute limit or a known 429 block raise a local
    `MapFlightsRateLimitError` without being sent.
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
        self._api_key = api_key.strip()
        self._session = session
        self._user_agent = user_agent
        self._base_url = URL(base_url)
        self._request_timeout = request_timeout
        self._throttle = throttle_for(self._api_key)
        self.attribution: str | None = None
        """Full attribution from the last `x-data-attribution` header."""
        self.live_rate_limit: RateLimitInfo | None = None
        """Rate-limit headers of the last live response (live-data bucket)."""
        self.daily_rate_limit: RateLimitInfo | None = None
        """Rate-limit headers of the last other response (daily quota)."""

    @property
    def key_prefix(self) -> str:
        """Prefix of the client's key."""
        return key_prefix(self._api_key)

    @property
    def remaining_today(self) -> int | None:
        """Daily quota left according to the last non-live response."""
        if self.daily_rate_limit is None:
            return None
        return self.daily_rate_limit.remaining

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
        response is the real number of aircraft in the radius. Live group:
        never counts against the daily quota.
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
            live=True,
        )
        return NearResponse.from_dict(data)

    async def me(self) -> Me:
        """State of the key: tariff, ceilings and today's usage.

        Experimental. Counts against the daily quota; meant for setup and
        diagnostics, not for polling.
        """
        return Me.from_dict(await self._request("/api/v1/me"))

    async def day_board(
        self,
        airport: str,
        direction: Literal["arr", "dep"],
        *,
        day: Literal[-1, 0, 1] = 0,
    ) -> DayBoard:
        """Arrivals or departures of an airport for one local day.

        Experimental. `airport` is an ICAO or IATA code; `day` is relative to
        the airport's local today. Not limited to the key's area.
        """
        airport = airport.strip().upper()
        if not _AIRPORT_RE.match(airport):
            raise ValueError("airport must be an ICAO or IATA code")
        if direction not in ("arr", "dep"):
            raise ValueError("direction must be 'arr' or 'dep'")
        if day not in (-1, 0, 1):
            raise ValueError("day must be -1, 0 or 1")
        data = await self._request(
            f"/api/v1/airports/{airport}/day-board",
            params={"dir": direction, "day": str(day)},
        )
        return DayBoard.from_dict(data)

    async def flight_by_callsign(self, callsign: str) -> FlightPage:
        """Return the current flight of an ICAO callsign or IATA flight number.

        Experimental. Raises `MapFlightsNoCurrentFlightError` when there is no
        current flight; that is a normal state and still counts against the
        daily quota.
        """
        callsign = callsign.replace(" ", "").upper()
        if not _CALLSIGN_RE.match(callsign):
            raise ValueError("callsign must be 2 to 10 letters or digits")
        try:
            data = await self._request(f"/api/v1/flights/by-callsign/{callsign}")
        except MapFlightsNotFoundError as err:
            reason = err.body.get("error")
            if reason not in _NO_CURRENT_FLIGHT:
                raise
            last_flight = err.body.get("lastFlight")
            raise MapFlightsNoCurrentFlightError(
                str(err),
                reason=reason,
                last_flight=last_flight if isinstance(last_flight, dict) else None,
                body=err.body,
            ) from err
        return FlightPage.from_dict(data)

    async def aircraft_flights(
        self, hex_id: str, *, limit: int | None = None
    ) -> AircraftFlights:
        """Recent flights of an airframe, newest first."""
        hex_id = hex_id.strip().lower()
        if not _HEX_RE.match(hex_id):
            raise ValueError("hex_id must be a 6-digit hex ICAO address")
        params: dict[str, str] = {}
        if limit is not None:
            if not 1 <= limit <= AIRCRAFT_FLIGHTS_MAX_LIMIT:
                raise ValueError(
                    f"limit must be between 1 and {AIRCRAFT_FLIGHTS_MAX_LIMIT}"
                )
            params["limit"] = str(limit)
        data = await self._request(f"/api/v1/aircraft/{hex_id}/flights", params=params)
        return AircraftFlights.from_dict(data)

    async def airlines(
        self,
        *,
        query: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> AirlinePage:
        """One page of the observed airlines (for ICAO code to name)."""
        params: dict[str, str] = {}
        if query is not None:
            params["q"] = query
        if limit is not None:
            if not 1 <= limit <= AIRLINES_MAX_LIMIT:
                raise ValueError(f"limit must be between 1 and {AIRLINES_MAX_LIMIT}")
            params["limit"] = str(limit)
        if offset:
            if offset < 0:
                raise ValueError("offset must not be negative")
            params["offset"] = str(offset)
        return AirlinePage.from_dict(
            await self._request("/api/v1/airlines", params=params)
        )

    async def _request(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        live: bool = False,
    ) -> dict[str, Any]:
        slot: AbstractAsyncContextManager[None]
        if live:
            slot = self._throttle.live()
        else:
            self._throttle.rest()
            slot = nullcontext()

        async with slot:
            try:
                _, body = await self._get(path, params, live=live)
            except MapFlightsRateLimitError as err:
                default = SCOPE_LIVE if live else SCOPE_MINUTE
                self._throttle.block(err.scope or default, err.retry_after)
                raise

        if not isinstance(body, dict):
            raise MapFlightsError("Unexpected response from map.flights")
        return body

    async def _get(
        self, path: str, params: dict[str, str] | None, *, live: bool
    ) -> tuple[ClientResponse, object]:
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
                    self._read_headers(response, live=live)
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
        return response, body

    def _read_headers(self, response: ClientResponse, *, live: bool) -> None:
        if attribution := response.headers.get(HEADER_ATTRIBUTION):
            self.attribution = attribution
        if HEADER_RATE_REMAINING not in response.headers:
            return
        info = RateLimitInfo(
            limit=_int_or_none(response.headers.get(HEADER_RATE_LIMIT)),
            remaining=_int_or_none(response.headers.get(HEADER_RATE_REMAINING)),
            reset_s=_int_or_none(response.headers.get(HEADER_RATE_RESET)),
        )
        if live:
            self.live_rate_limit = info
        else:
            self.daily_rate_limit = info

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
            return MapFlightsNotFoundError(message, body=info)
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
