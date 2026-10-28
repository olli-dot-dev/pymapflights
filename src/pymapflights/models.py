"""Data models of the map.flights API.

Derived from the OpenAPI specification (`/api/v1/openapi.json`). Unknown fields
are ignored, because stable operations may gain fields within `/api/v1`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from mashumaro import DataClassDictMixin, field_options
from mashumaro.types import SerializationStrategy


class UnixMillis(SerializationStrategy):
    """Unix milliseconds (UTC) as an aware datetime."""

    def serialize(self, value: datetime) -> int:
        """Convert a datetime to Unix milliseconds."""
        return int(value.timestamp() * 1000)

    def deserialize(self, value: int) -> datetime:
        """Convert Unix milliseconds to an aware datetime."""
        return datetime.fromtimestamp(value / 1000, tz=UTC)


@dataclass(frozen=True)
class RateLimitInfo:
    """Rate-limit headers of the last response.

    For `/live` and `/near` the values describe the live-data bucket, for all
    other endpoints the daily quota.
    """

    limit: int | None
    remaining: int | None
    reset_s: int | None


@dataclass(frozen=True)
class NearAircraft(DataClassDictMixin):
    """One aircraft of `GET /near`. Units: ft, kt, degrees, km."""

    hex: str
    lat: float
    lon: float
    alt_baro: int | None = field(metadata=field_options(alias="altBaro"))
    """Barometric altitude in ft; None = on ground or unknown."""
    on_ground: bool = field(metadata=field_options(alias="onGround"))
    gs: float | None
    """Ground speed in kt."""
    track: float | None
    """Track over ground in degrees."""
    callsign: str | None
    registration: str | None
    typecode: str | None
    """ICAO type code."""
    airline_icao: str | None = field(metadata=field_options(alias="airlineIcao"))
    """Airline ICAO derived from the callsign prefix."""
    category: str | None
    """ADS-B emitter category A0-D7."""
    kind: str
    """airline, cargo, biz, ga, heli, mil, other or ground (may grow)."""
    emergency: str | None
    origin: str | None
    """Origin ICAO from the callsign mapping (candidate, not observed)."""
    dest: str | None
    """Destination ICAO from the callsign mapping (candidate, not observed)."""
    distance_km: float = field(metadata=field_options(alias="distanceKm"))
    bearing: float
    """Bearing from the query point in degrees from north."""
    age_s: int | None = field(default=None, metadata=field_options(alias="ageS"))
    """Age of the last real observation in seconds, relative to `now`."""
    estimated: bool = field(default=False, metadata=field_options(alias="est"))
    """Position is estimated outside coverage."""
    ground_object: bool = field(default=False, metadata=field_options(alias="gndObj"))
    """Unknown ground object, not an aircraft."""
    gs_estimated: bool = field(default=False, metadata=field_options(alias="gsEst"))
    track_estimated: bool = field(
        default=False, metadata=field_options(alias="trackEst")
    )

    class Config:
        """mashumaro options."""

        serialize_by_alias = True

    @classmethod
    def __pre_deserialize__(cls, d: dict[str, object]) -> dict[str, object]:
        """Treat `null` flags as absent (the live diff sends `null` to clear)."""
        for key in ("est", "gndObj", "gsEst", "trackEst"):
            if d.get(key) is None:
                d.pop(key, None)
        return d


@dataclass(frozen=True)
class NearResponse(DataClassDictMixin):
    """Response of `GET /near/{lat}/{lon}/{radius}`."""

    now: datetime = field(metadata=field_options(serialization_strategy=UnixMillis()))
    """Server time of the snapshot."""
    total: int
    """Aircraft within the radius in total; `aircraft` is capped by `limit`."""
    aircraft: list[NearAircraft] = field(metadata=field_options(alias="ac"))
    """Nearest aircraft first, at most `limit` entries."""
    data_delay_s: int | None = field(
        default=None, metadata=field_options(alias="dataDelayS")
    )
    """Tariff delays all data by this many seconds; None = live data."""
    data_delay_ready: bool | None = field(
        default=None, metadata=field_options(alias="dataDelayReady")
    )

    class Config:
        """mashumaro options."""

        serialize_by_alias = True

    @property
    def ready(self) -> bool:
        """False while a delay buffer is still filling (`aircraft` is then empty).

        An empty list in that state does not mean there is no traffic.
        """
        return self.data_delay_ready is not False

    @property
    def truncated(self) -> bool:
        """True when more aircraft are in the radius than were returned."""
        return self.total > len(self.aircraft)
