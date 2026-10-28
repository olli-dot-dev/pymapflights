"""Tests for GET /near."""

from datetime import UTC, datetime

import pytest
from aiohttp import ClientSession

from pymapflights import (
    MapFlights,
    MapFlightsAuthError,
    MapFlightsConnectionError,
    MapFlightsError,
    MapFlightsKeyDormantError,
    MapFlightsNotFoundError,
    MapFlightsNotInTariffError,
    MapFlightsOutOfAreaError,
    MapFlightsRateLimitError,
    MapFlightsTariffError,
    RateLimitInfo,
)

from .conftest import FakeApi, load_fixture


async def test_near(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(
        load_fixture("near.json"),
        headers={
            "x-data-attribution": "Data: map.flights, adsb.fi",
            "X-RateLimit-Limit": "1",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "5",
        },
    )

    result = await client.near(48.11, 16.57, 25)

    assert result.now == datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    assert result.total == 3
    assert result.truncated
    assert result.ready
    assert result.data_delay_s is None

    first, second = result.aircraft
    assert first.hex == "440170"
    assert first.callsign == "AUA711"
    assert first.alt_baro == 3250
    assert first.airline_icao == "AUA"
    assert first.distance_km == 4.21
    assert first.origin == "LOWW"
    assert not first.on_ground
    assert not first.ground_object
    assert not first.estimated

    assert second.alt_baro is None
    assert second.on_ground
    assert second.ground_object
    assert not second.estimated

    assert client.attribution == "Data: map.flights, adsb.fi"
    assert client.rate_limit == RateLimitInfo(limit=1, remaining=0, reset_s=5)


async def test_request_headers(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(load_fixture("near.json"))

    await client.near(48.11, 16.57, 25, limit=100)

    request = fake_api.last
    assert request.path == "/api/v1/near/48.11/16.57/25"
    assert request.query["limit"] == "100"
    headers = request.headers
    assert headers["x-api-key"] == "test-key"
    assert headers["User-Agent"] == "test-agent/1.0"
    assert client.rate_limit is None


async def test_coordinates_rounded(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(
        load_fixture("near.json"),
    )

    await client.near(48.123456789, 16.0, 12.5)

    assert fake_api.last.path == "/api/v1/near/48.12346/16.0/12.5"


async def test_delay_buffer_filling(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(
        {
            "now": 1793188800000,
            "total": 0,
            "ac": [],
            "dataDelayS": 60,
            "dataDelayReady": False,
        },
    )

    result = await client.near(48.11, 16.57, 25)

    assert not result.ready
    assert result.data_delay_s == 60
    assert not result.truncated


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"lat": 91, "lon": 0, "radius_km": 25}, "lat"),
        ({"lat": 0, "lon": -181, "radius_km": 25}, "lon"),
        ({"lat": 0, "lon": 0, "radius_km": 0}, "radius_km"),
        ({"lat": 0, "lon": 0, "radius_km": 501}, "radius_km"),
        ({"lat": 0, "lon": 0, "radius_km": 25, "limit": 0}, "limit"),
        ({"lat": 0, "lon": 0, "radius_km": 25, "limit": 501}, "limit"),
    ],
)
async def test_invalid_arguments(
    client: MapFlights, kwargs: dict[str, float], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        await client.near(**kwargs)  # type: ignore[arg-type]


async def test_auth_error(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(
        status=401,
        payload={
            "statusCode": 401,
            "error": "Unauthorized",
            "code": "invalid_key",
            "message": "Unknown or revoked API key",
            "notice": "...",
        },
    )

    with pytest.raises(MapFlightsAuthError, match="Unknown or revoked"):
        await client.near(48.11, 16.57, 25)


@pytest.mark.parametrize(
    ("code", "error"),
    [
        ("out_of_area", MapFlightsOutOfAreaError),
        ("key_dormant", MapFlightsKeyDormantError),
        ("group_not_in_tariff", MapFlightsNotInTariffError),
        ("endpoint_not_in_tariff", MapFlightsNotInTariffError),
        ("format_not_in_tariff", MapFlightsNotInTariffError),
        ("something_new", MapFlightsTariffError),
    ],
)
async def test_tariff_errors(
    fake_api: FakeApi,
    client: MapFlights,
    code: str,
    error: type[MapFlightsTariffError],
) -> None:
    fake_api.reply(
        status=403,
        payload={
            "statusCode": 403,
            "error": "Forbidden",
            "code": code,
            "tariff": "feeder",
            "message": "Denied",
            "attribution": "Data: map.flights",
        },
    )

    with pytest.raises(error) as exc_info:
        await client.near(48.11, 16.57, 25)

    assert type(exc_info.value) is error
    assert exc_info.value.code == code
    assert exc_info.value.tariff == "feeder"


async def test_forbidden_without_body(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(status=403, text="nope")

    with pytest.raises(MapFlightsTariffError) as exc_info:
        await client.near(48.11, 16.57, 25)

    assert exc_info.value.code == "forbidden"
    assert exc_info.value.tariff is None


async def test_not_found(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(status=404, payload={"error": "not found"})

    with pytest.raises(MapFlightsNotFoundError, match="not found"):
        await client.near(48.11, 16.57, 25)


async def test_rate_limit(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(
        status=429,
        headers={"Retry-After": "4"},
        payload={
            "statusCode": 429,
            "error": "Too Many Requests",
            "code": "rate_limited",
            "scope": "live",
            "limit": 1,
            "retryAfterS": 4,
            "message": "Slow down",
            "attribution": "Data: map.flights",
        },
    )

    with pytest.raises(MapFlightsRateLimitError) as exc_info:
        await client.near(48.11, 16.57, 25)

    assert exc_info.value.retry_after == 4
    assert exc_info.value.scope == "live"
    assert exc_info.value.limit == 1


async def test_rate_limit_header_unparsable(
    fake_api: FakeApi, client: MapFlights
) -> None:
    fake_api.reply(
        {"code": "rate_limited", "scope": "day", "limit": 1000, "retryAfterS": 3600},
        status=429,
        headers={"Retry-After": "soon"},
    )

    with pytest.raises(MapFlightsRateLimitError) as exc_info:
        await client.near(48.11, 16.57, 25)

    assert exc_info.value.retry_after == 3600
    assert exc_info.value.scope == "day"


async def test_rate_limit_plain(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(
        status=429,
        payload={"statusCode": 429, "error": "Too Many Requests", "message": "x"},
    )

    with pytest.raises(MapFlightsRateLimitError) as exc_info:
        await client.near(48.11, 16.57, 25)

    assert exc_info.value.retry_after is None
    assert exc_info.value.scope is None


async def test_server_error(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(status=500, text="boom")

    with pytest.raises(MapFlightsError, match="HTTP 500"):
        await client.near(48.11, 16.57, 25)


async def test_not_json(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(status=200, text="<html>", content_type="text/html")

    with pytest.raises(MapFlightsError, match="JSON"):
        await client.near(48.11, 16.57, 25)


async def test_unexpected_json(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(status=200, payload=[1, 2])

    with pytest.raises(MapFlightsError, match="Unexpected"):
        await client.near(48.11, 16.57, 25)


async def test_timeout(fake_api: FakeApi, api: tuple[FakeApi, str]) -> None:
    fake_api.delay = 1

    async with ClientSession() as session:
        client = MapFlights(
            "test-key", session=session, base_url=api[1], request_timeout=0.05
        )
        with pytest.raises(MapFlightsConnectionError, match="Timeout"):
            await client.near(48.11, 16.57, 25)


async def test_connection_error() -> None:
    async with ClientSession() as session:
        client = MapFlights("test-key", session=session, base_url="http://127.0.0.1:9")
        with pytest.raises(MapFlightsConnectionError, match="Error while talking"):
            await client.near(48.11, 16.57, 25)


async def test_default_user_agent(fake_api: FakeApi, api: tuple[FakeApi, str]) -> None:
    fake_api.reply(load_fixture("near.json"))

    async with ClientSession() as session:
        await MapFlights("k", session=session, base_url=api[1]).near(1, 2, 3)

    assert fake_api.last.headers["User-Agent"].startswith("pymapflights/")
