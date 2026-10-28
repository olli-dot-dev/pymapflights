"""Exceptions raised by the map.flights API client."""


class MapFlightsError(Exception):
    """Base error of the map.flights client."""


class MapFlightsConnectionError(MapFlightsError):
    """The API could not be reached or did not answer in time."""


class MapFlightsAuthError(MapFlightsError):
    """The API key is unknown or revoked (401 `invalid_key`)."""


class MapFlightsNotFoundError(MapFlightsError):
    """The requested object does not exist (404)."""


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
    """A rate limit was exceeded (429)."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: int | None,
        scope: str | None,
        limit: int | None,
    ) -> None:
        """Initialize with the wait time and which ceiling was hit."""
        super().__init__(message)
        self.retry_after = retry_after
        self.scope = scope
        self.limit = limit
