"""Asynchronous Python client for the map.flights API (unofficial)."""

from .client import MapFlights
from .const import VERSION
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
from .models import NearAircraft, NearResponse, RateLimitInfo

__version__ = VERSION

__all__ = [
    "MapFlights",
    "MapFlightsAuthError",
    "MapFlightsConnectionError",
    "MapFlightsError",
    "MapFlightsKeyDormantError",
    "MapFlightsNotFoundError",
    "MapFlightsNotInTariffError",
    "MapFlightsOutOfAreaError",
    "MapFlightsRateLimitError",
    "MapFlightsTariffError",
    "NearAircraft",
    "NearResponse",
    "RateLimitInfo",
    "__version__",
]
