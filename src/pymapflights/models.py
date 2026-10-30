"""Data models of the map.flights API.

Derived from the OpenAPI specification (`/api/v1/openapi.json`). Unknown fields
are ignored, because stable operations may gain fields within `/api/v1`.
Models of experimental operations make every field optional, because those
operations may change within `/api/v1`.
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


class _Model(DataClassDictMixin):
    """Base of all API models: camelCase aliases, timestamps as datetime."""

    class Config:
        """mashumaro options."""

        serialize_by_alias = True
        serialization_strategy = {datetime: UnixMillis()}  # noqa: RUF012


@dataclass(frozen=True)
class RateLimitInfo:
    """`X-RateLimit-*` headers of a response."""

    limit: int | None
    remaining: int | None
    reset_s: int | None
    """Seconds until the ceiling resets (00:00 UTC for the daily quota)."""


# --- /near ------------------------------------------------------------------


@dataclass(frozen=True)
class NearAircraft(_Model):
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

    @classmethod
    def __pre_deserialize__(cls, d: dict[str, object]) -> dict[str, object]:
        """Treat `null` flags as absent (the live diff sends `null` to clear)."""
        for key in ("est", "gndObj", "gsEst", "trackEst"):
            if d.get(key) is None:
                d.pop(key, None)
        return d


@dataclass(frozen=True)
class NearResponse(_Model):
    """Response of `GET /near/{lat}/{lon}/{radius}`."""

    now: datetime
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


# --- /me (experimental) -------------------------------------------------------


@dataclass(frozen=True)
class MeKey(_Model):
    """The calling key. `label` is internal text and deliberately not mapped."""

    prefix: str
    tier: str | None = None
    created: datetime | None = None


@dataclass(frozen=True)
class MeTariff(_Model):
    """Tariff of the key. The spec leaves the object open; `id` is per operator."""

    id: str | None = None
    dormant: bool | None = None
    """The station operator key sleeps (no station data for 7 days)."""


@dataclass(frozen=True)
class MeLimits(_Model):
    """Ceilings of the key."""

    per_minute: int | None = field(
        default=None, metadata=field_options(alias="perMinute")
    )
    per_day: int | None = field(default=None, metadata=field_options(alias="perDay"))


@dataclass(frozen=True)
class MeUsage(_Model):
    """Today's usage of the key."""

    day: str | None = None
    """UTC day the counters belong to."""
    total: int | None = None
    remaining_day: int | None = field(
        default=None, metadata=field_options(alias="remainingDay")
    )
    reset_s: int | None = field(default=None, metadata=field_options(alias="resetS"))
    """Seconds until the quota resets (00:00 UTC)."""


@dataclass(frozen=True)
class MeStation(_Model):
    """One station of the account the key belongs to."""

    id: int | None = None
    slug: str | None = None
    """`station-<id>`, the slug of the station profile."""
    name: str | None = None
    """Public name; None = the operator did not choose one."""
    feeding_now: bool | None = field(
        default=None, metadata=field_options(alias="feedingNow")
    )
    """The station sent data in the last 2 minutes."""
    last_seen: datetime | None = field(
        default=None, metadata=field_options(alias="lastSeen")
    )
    active: bool | None = None
    """Data in the last 7 days; keeps a station operator key awake."""


@dataclass(frozen=True)
class MeAreaCircle(_Model):
    """One circle of the live-data area of a key. Units: degrees, km.

    A station circle is centred on the station's 25 km grid cell, a home key
    circle on the chosen place rounded to 0.01 degrees.
    """

    lat: float
    lon: float
    radius_km: float = field(metadata=field_options(alias="radiusKm"))
    kind: str | None = None
    """`station`, `area` or `home`."""
    label: str | None = None
    reach_km: float | None = field(
        default=None, metadata=field_options(alias="reachKm")
    )
    """Measured typical range of the station, when known."""


@dataclass(frozen=True)
class Me(_Model):
    """Response of `GET /me`."""

    key: MeKey
    limits: MeLimits = field(default_factory=MeLimits)
    usage: MeUsage = field(default_factory=MeUsage)
    tariff: MeTariff | None = None
    account_id: str | None = field(
        default=None, metadata=field_options(alias="accountId")
    )
    """Stable opaque id of the account; survives a new key. Not a secret."""
    stations: list[MeStation] | None = None
    """Stations of the account; None = key without an account."""
    area: list[MeAreaCircle] | None = None
    """Live-data area as circles; `[]` = nowhere right now (sleeping key).

    None = not reported (no tariff, tariff by continent) or the whole world,
    see `area_worldwide`.
    """
    area_worldwide: bool = field(
        default=False, metadata=field_options(alias="_areaWorldwide")
    )
    """The API sent `area: null`: live data for the whole world."""
    attribution: str | None = None

    @classmethod
    def __pre_deserialize__(cls, d: dict[str, object]) -> dict[str, object]:
        """Keep `area: null` (whole world) apart from a missing `area`."""
        d = {k: v for k, v in d.items() if k != "_areaWorldwide"}
        if "area" in d and d["area"] is None:
            d["_areaWorldwide"] = True
        return d

    @property
    def tariff_id(self) -> str | None:
        """`home` or `feeder`: `tariff.id`, falling back to `key.tier`."""
        if self.tariff is not None and self.tariff.id:
            return self.tariff.id
        return self.key.tier


# --- shared ----------------------------------------------------------------


@dataclass(frozen=True)
class AirportRef(_Model):
    """Airport as referenced from flights and boards."""

    icao: str
    iata: str | None = None
    name: str | None = None
    municipality: str | None = None
    country: str | None = None
    """ISO 3166-1 alpha-2 country code."""
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class FlightSummary(_Model):
    """One flight as built from observed positions.

    `takeoff_time` and `landing_time` are measured by map.flights; a landing
    appears 20 to 35 minutes after touchdown, and only where receivers see the
    airport down to the ground.
    """

    id: int | None
    """Flight id; None while the flight is still being assembled."""
    hex: str | None = None
    callsign: str | None = None
    registration: str | None = None
    typecode: str | None = None
    airline_icao: str | None = field(
        default=None, metadata=field_options(alias="airlineIcao")
    )
    origin: AirportRef | None = None
    dest: AirportRef | None = None
    first_seen: datetime | None = field(
        default=None, metadata=field_options(alias="firstSeen")
    )
    last_seen: datetime | None = field(
        default=None, metadata=field_options(alias="lastSeen")
    )
    takeoff_time: datetime | None = field(
        default=None, metadata=field_options(alias="takeoffTime")
    )
    landing_time: datetime | None = field(
        default=None, metadata=field_options(alias="landingTime")
    )
    completeness: str | None = None
    """complete, no_takeoff, no_landing or mid_air_only."""
    classification: str | None = None
    diverted: bool = False


# --- /aircraft/{hex}/flights ----------------------------------------------------


@dataclass(frozen=True)
class AircraftFlights(_Model):
    """Response of `GET /aircraft/{hex}/flights`, newest first."""

    hex: str
    flights: list[FlightSummary]


# --- /flights/by-callsign (experimental) -----------------------------------------


@dataclass(frozen=True)
class LiveState(_Model):
    """Live state of the flight in progress. Units: ft, kt, ft/min."""

    hex: str | None = None
    callsign: str | None = None
    lat: float | None = None
    lon: float | None = None
    alt_baro: int | None = field(default=None, metadata=field_options(alias="altBaro"))
    on_ground: bool | None = field(
        default=None, metadata=field_options(alias="onGround")
    )
    gs: float | None = None
    track: float | None = None
    baro_rate: float | None = field(
        default=None, metadata=field_options(alias="baroRate")
    )
    squawk: str | None = None
    emergency: str | None = None
    updated: datetime | None = None


@dataclass(frozen=True)
class Delay(_Model):
    """Delay of one end of a flight against the plan."""

    band: str | None = None
    """early, on_time, delayed_15, delayed_30, delayed_60; None = unknown."""
    minutes: int | None = None
    """Deviation in minutes, positive = late."""
    estimated: bool = False
    """The minute figure is an estimate: show the band, not the number."""
    basis: str | None = None
    """schedule (airport feed) or baseline (median of observations)."""
    sched_time: datetime | None = field(
        default=None, metadata=field_options(alias="schedTime")
    )
    est_time: datetime | None = field(
        default=None, metadata=field_options(alias="estTime")
    )
    actual_time: datetime | None = field(
        default=None, metadata=field_options(alias="actualTime")
    )
    status: str | None = None


@dataclass(frozen=True)
class FlightDelay(_Model):
    """Departure and arrival delay of a flight."""

    dep: Delay | None = None
    arr: Delay | None = None


@dataclass(frozen=True)
class FlightPage(_Model):
    """Response of `GET /flights/by-callsign/{callsign}`."""

    now: datetime | None = None
    flight: FlightSummary | None = None
    live: LiveState | None = None
    """Present only while this flight is the one in progress."""
    delay: FlightDelay | None = None


# --- /airports/{icao}/day-board (experimental) -------------------------------------


@dataclass(frozen=True)
class Attribution(_Model):
    """Source credit of a board."""

    text: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class DayBoardRow(_Model):
    """One row of an airport day board."""

    key: str
    basis: str | None = None
    """board (live board), schedule (timetable), usual (learned) or observed."""
    plan_time: datetime | None = field(
        default=None, metadata=field_options(alias="planTime")
    )
    est_time: datetime | None = field(
        default=None, metadata=field_options(alias="estTime")
    )
    measured_time: datetime | None = field(
        default=None, metadata=field_options(alias="measuredTime")
    )
    """Take-off or landing measured by map.flights, never a board time."""
    seen_time: datetime | None = field(
        default=None, metadata=field_options(alias="seenTime")
    )
    flight_number: str | None = field(
        default=None, metadata=field_options(alias="flightNumber")
    )
    callsign: str | None = None
    codeshares: list[str] | None = None
    airline_icao: str | None = field(
        default=None, metadata=field_options(alias="airlineIcao")
    )
    airline_iata: str | None = field(
        default=None, metadata=field_options(alias="airlineIata")
    )
    airline_name: str | None = field(
        default=None, metadata=field_options(alias="airlineName")
    )
    counterpart: AirportRef | None = None
    """Origin for arrivals, destination for departures."""
    gate: str | None = None
    terminal: str | None = None
    belt: str | None = None
    status: str | None = None
    band: str | None = None
    """early, on_time, delayed_15, delayed_30, delayed_60; None = unknown."""
    band_basis: str | None = field(
        default=None, metadata=field_options(alias="bandBasis")
    )
    typecode: str | None = None
    flight_id: int | None = field(
        default=None, metadata=field_options(alias="flightId")
    )


@dataclass(frozen=True)
class DayBoard(_Model):
    """Response of `GET /airports/{icao}/day-board`."""

    icao: str
    iata: str | None = None
    name: str | None = None
    tz: str | None = None
    """IANA time zone of the airport."""
    dir: str | None = None
    day: int | None = None
    date: str | None = None
    """Local date of the day (YYYY-MM-DD)."""
    from_time: datetime | None = field(
        default=None, metadata=field_options(alias="from")
    )
    to_time: datetime | None = field(default=None, metadata=field_options(alias="to"))
    generated_at: datetime | None = field(
        default=None, metadata=field_options(alias="generatedAt")
    )
    source: str | None = None
    """feed, observed or none (nothing known, rows empty)."""
    rows: list[DayBoardRow] = field(default_factory=list)
    truncated: bool = False
    attribution: Attribution | None = None
    board_fetched: datetime | None = field(
        default=None, metadata=field_options(alias="boardFetched")
    )


# --- /airlines -----------------------------------------------------------------


@dataclass(frozen=True)
class Airline(_Model):
    """One airline of `GET /airlines`."""

    icao: str
    iata: str | None = None
    name: str | None = None
    country: str | None = None


@dataclass(frozen=True)
class AirlinePage(_Model):
    """One page of `GET /airlines`."""

    total: int
    items: list[Airline]
