"""Tests for /me, day-board, by-callsign, aircraft flights and airlines."""

from datetime import UTC, datetime

import pytest

from pymapflights import (
    MapFlights,
    MapFlightsNoCurrentFlightError,
    MapFlightsNotFoundError,
    MeAreaCircle,
    MeStation,
    RateLimitInfo,
    key_prefix,
)

from .conftest import TEST_KEY, FakeApi, load_fixture

DAILY_HEADERS = {
    "X-RateLimit-Limit": "1000",
    "X-RateLimit-Remaining": "987",
    "X-RateLimit-Reset": "43200",
}


def test_key_prefix() -> None:
    assert key_prefix(TEST_KEY) == "mf_live_0123abcd"
    assert key_prefix(f"  {TEST_KEY}\n") == "mf_live_0123abcd"
    with pytest.raises(ValueError, match="too short"):
        key_prefix("mf_live_12")


def test_client_key_prefix(client: MapFlights) -> None:
    assert client.key_prefix == "mf_live_0123abcd"


async def test_me(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(load_fixture("me.json"), headers=DAILY_HEADERS)

    me = await client.me()

    assert fake_api.last.path == "/api/v1/me"
    assert me.key.prefix == "mf_live_0123abcd"
    assert me.key.created == datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    assert me.tariff_id == "home"
    assert me.limits.per_minute == 60
    assert me.usage.remaining_day == 988
    assert not hasattr(me.key, "label")
    assert me.tariff is not None
    assert me.tariff.dormant is False
    assert me.account_id == "6f1c2e7a-3b4d-4e5f-8a9b-0c1d2e3f4a5b"
    assert me.stations == [
        MeStation(
            id=42,
            slug="station-42",
            name=None,
            feeding_now=True,
            last_seen=datetime(2026, 10, 28, 12, 0, tzinfo=UTC),
            active=True,
        )
    ]
    assert me.area == [
        MeAreaCircle(lat=48.21, lon=16.37, radius_km=50, kind="home", label="Home")
    ]
    assert me.area_worldwide is False
    assert client.daily_rate_limit == RateLimitInfo(
        limit=1000, remaining=987, reset_s=43200
    )
    assert client.remaining_today == 987
    assert client.live_rate_limit is None


@pytest.mark.parametrize(
    ("tariff", "expected"),
    [(None, "feeder"), ({}, "feeder"), ({"id": None}, "feeder")],
)
async def test_me_tariff_falls_back_to_tier(
    fake_api: FakeApi, client: MapFlights, tariff: object, expected: str
) -> None:
    data = load_fixture("me.json")
    data["tariff"] = tariff
    fake_api.reply(data)

    assert (await client.me()).tariff_id == expected


async def test_me_minimal(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply({"key": {"prefix": "mf_live_0123abcd"}})

    me = await client.me()

    assert me.tariff_id is None
    assert me.usage.remaining_day is None
    assert me.account_id is None
    assert me.stations is None
    assert me.area is None
    assert me.area_worldwide is False
    assert client.remaining_today is None


@pytest.mark.parametrize(
    ("area", "circles", "worldwide"),
    [(None, None, True), ([], [], False)],
)
async def test_me_area_world_and_nowhere(
    fake_api: FakeApi,
    client: MapFlights,
    area: list[object] | None,
    circles: list[MeAreaCircle] | None,
    *,
    worldwide: bool,
) -> None:
    fake_api.reply({"key": {"prefix": "mf_live_0123abcd"}, "area": area})

    me = await client.me()

    assert me.area == circles
    assert me.area_worldwide is worldwide


async def test_me_ignores_injected_worldwide_flag(
    fake_api: FakeApi, client: MapFlights
) -> None:
    fake_api.reply({"key": {"prefix": "mf_live_0123abcd"}, "_areaWorldwide": True})

    assert (await client.me()).area_worldwide is False


async def test_day_board(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(load_fixture("day_board.json"), headers=DAILY_HEADERS)

    board = await client.day_board(" vie ", "dep", day=1)

    assert fake_api.last.path == "/api/v1/airports/VIE/day-board"
    assert dict(fake_api.last.query) == {"dir": "dep", "day": "1"}
    assert board.icao == "LOWW"
    assert board.source == "feed"
    assert board.attribution is not None
    assert board.attribution.text == "Flughafen Wien"
    assert board.from_time == datetime(2026, 10, 27, 23, 0, tzinfo=UTC)

    first, second = board.rows
    assert first.basis == "board"
    assert first.flight_number == "OS711"
    assert first.band == "delayed_15"
    assert first.counterpart is not None
    assert first.counterpart.iata == "CDG"
    assert first.measured_time is None
    assert first.codeshares == ["LH6321"]
    assert second.basis == "usual"
    assert second.counterpart is None


async def test_day_board_nothing_known(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply({"icao": "LKMT", "source": "none", "rows": []})

    board = await client.day_board("LKMT", "arr")

    assert dict(fake_api.last.query) == {"dir": "arr", "day": "0"}
    assert board.rows == []
    assert not board.truncated


@pytest.mark.parametrize(
    ("args", "match"),
    [
        (("V!", "dep", 0), "airport"),
        (("LOWW", "both", 0), "direction"),
        (("LOWW", "dep", 2), "day"),
    ],
)
async def test_day_board_invalid(
    client: MapFlights, args: tuple[str, str, int], match: str
) -> None:
    airport, direction, day = args
    with pytest.raises(ValueError, match=match):
        await client.day_board(airport, direction, day=day)  # type: ignore[arg-type]


async def test_flight_by_callsign(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(load_fixture("by_callsign.json"))

    page = await client.flight_by_callsign("os 711")

    assert fake_api.last.path == "/api/v1/flights/by-callsign/OS711"
    assert page.flight is not None
    assert page.flight.id is None
    assert page.flight.hex == "440170"
    assert page.flight.takeoff_time == datetime(2026, 10, 28, 11, 50, tzinfo=UTC)
    assert page.flight.landing_time is None
    assert page.flight.origin is not None
    assert page.flight.origin.icao == "LOWW"
    assert page.live is not None
    assert page.live.on_ground is False
    assert page.live.baro_rate == 1800
    assert page.live.squawk == "4621"
    assert page.delay is not None
    assert page.delay.dep is not None
    assert page.delay.dep.minutes == 18
    assert page.delay.arr is None


async def test_no_current_flight(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(
        {
            "error": "no current flight",
            "routeId": 42,
            "lastFlight": {"id": 1, "callsign": "AUA711"},
            "previous": [],
        },
        status=404,
    )

    with pytest.raises(MapFlightsNoCurrentFlightError) as exc_info:
        await client.flight_by_callsign("AUA711")

    assert exc_info.value.reason == "no current flight"
    assert exc_info.value.last_flight == {"id": 1, "callsign": "AUA711"}
    assert exc_info.value.body["routeId"] == 42


async def test_unknown_flight(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply({"error": "unknown flight"}, status=404)

    with pytest.raises(MapFlightsNoCurrentFlightError) as exc_info:
        await client.flight_by_callsign("XYZ999")

    assert exc_info.value.reason == "unknown flight"
    assert exc_info.value.last_flight is None


async def test_by_callsign_other_404(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply({"error": "something else"}, status=404)

    with pytest.raises(MapFlightsNotFoundError) as exc_info:
        await client.flight_by_callsign("XYZ999")

    assert type(exc_info.value) is MapFlightsNotFoundError


async def test_by_callsign_invalid(client: MapFlights) -> None:
    with pytest.raises(ValueError, match="callsign"):
        await client.flight_by_callsign("A")


async def test_aircraft_flights(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(load_fixture("aircraft_flights.json"))

    result = await client.aircraft_flights("44017A", limit=5)

    assert fake_api.last.path == "/api/v1/aircraft/44017a/flights"
    assert fake_api.last.query["limit"] == "5"
    (flight,) = result.flights
    assert flight.id == 987654
    assert flight.completeness == "complete"
    assert flight.landing_time is not None
    assert flight.dest is not None
    assert flight.dest.icao == "LOWW"


@pytest.mark.parametrize(
    ("hex_id", "limit", "match"),
    [("44017", None, "hex_id"), ("44017g", None, "hex_id"), ("440170", 51, "limit")],
)
async def test_aircraft_flights_invalid(
    client: MapFlights, hex_id: str, limit: int | None, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        await client.aircraft_flights(hex_id, limit=limit)


async def test_airlines(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(load_fixture("airlines.json"))

    page = await client.airlines(query="aus", limit=200, offset=200)

    assert dict(fake_api.last.query) == {"q": "aus", "limit": "200", "offset": "200"}
    assert page.total == 2
    assert page.items[0].name == "Austrian Airlines"
    assert page.items[1].name is None


async def test_airlines_defaults(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(load_fixture("airlines.json"))

    await client.airlines()

    assert dict(fake_api.last.query) == {}


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [({"limit": 0}, "limit"), ({"limit": 201}, "limit"), ({"offset": -1}, "offset")],
)
async def test_airlines_invalid(
    client: MapFlights, kwargs: dict[str, int], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        await client.airlines(**kwargs)  # type: ignore[arg-type]
