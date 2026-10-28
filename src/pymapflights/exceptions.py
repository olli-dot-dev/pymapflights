"""Exceptions raised by the map.flights API client."""

from typing import Any


class MapFlightsError(Exception):
    """Base error of the map.flights client."""


class MapFlightsConnectionError(MapFlightsError):
    """The API could not be reached or did not answer in time."""


class MapFlightsAuthError(MapFlightsError):
    """The API key is unknown or revoked (401 `invalid_key`)."""


class MapFlightsNotFoundError(MapFlightsError):
    """The requested object does not exist (404). Counts against the quota."""

    def __init__(self, message: str, *, body: dict[str, Any] | None = None) -> None:
        """Initialize with the parsed error body."""
        super().__init__(message)
        self.body: dict[str, Any] = body or {}


class MapFlightsNoCurrentFlightError(MapFlightsNotFoundError):
    """No current flight under a callsign (404 of `by-callsign`).

    A normal state when tracking, not a failure. `reason` is `no current flight`
    (only a flight older than 6 hours exists, see `last_flight`) or
    `unknown flight` (nobody transmits the callsign and no flight is known).
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        last_flight: dict[str, Any] | None,
        body: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with the reason and the raw last flight (untyped in the spec)."""
        super().__init__(message, body=body)
        self.reason = reason
        self.last_flight = last_flight


class MapFlightsTariffError(MapFlightsError):
    """The key's tariff denies the request (403)."""

    def __init__(self, message: str, *, code: str, tariff: str | None) -> None:
        """Initialize with the machine-readable code and the key's tariff."""
        super().__init__(message)
        self.code = code
        self.tariff = tariff


class MapFlightsOutOfAreaError(MapFlightsTariffError):
    """The request lies completely outside the key's area (403 `out_of_area`)."""


class MapFlightsKeyDormantError(MapFlightsTariffError):
    """No station of the key's owner sent data for 7 days (403 `key_dormant`)."""


class MapFlightsNotInTariffError(MapFlightsTariffError):
    """The endpoint, its group or the format is not part of the tariff."""


class MapFlightsRateLimitError(MapFlightsError):
    """A rate limit was exceeded (429), or the client refused to exceed it.

    `scope` is `live`, `minute` or `day`. With `local` the request was never
    sent because the client knows it would be rejected.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: int | None,
        scope: str | None,
        limit: int | None,
        local: bool = False,
    ) -> None:
        """Initialize with the wait time and which ceiling was hit."""
        super().__init__(message)
        self.local = local
        self.retry_after = retry_after
        self.scope = scope
        self.limit = limit
