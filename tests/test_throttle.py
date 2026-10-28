"""Tests for the client-side rate limits."""

import time

import pytest
from aiohttp import ClientSession

from pymapflights import MapFlights, MapFlightsOutOfAreaError, MapFlightsRateLimitError
from pymapflights import throttle as throttle_module

from .conftest import TEST_KEY, FakeApi, load_fixture

NEAR = (48.11, 16.57, 25)


def rate_limited(scope: str | None, retry_after: int) -> dict[str, object]:
    body: dict[str, object] = {
        "statusCode": 429,
        "error": "Too Many Requests",
        "message": "Slow down",
    }
    if scope is not None:
        body |= {"code": "rate_limited", "scope": scope, "limit": 1}
    body["retryAfterS"] = retry_after
    return body


async def test_live_requests_keep_interval(
    fake_api: FakeApi, client: MapFlights
) -> None:
    fake_api.reply(load_fixture("near.json"))

    start = time.monotonic()
    await client.near(*NEAR)
    await client.near(*NEAR)
    await client.near(*NEAR)

    assert time.monotonic() - start >= 2 * throttle_module.LIVE_INTERVAL_S
    assert len(fake_api.requests) == 3


async def test_live_slot_used_by_failed_request(
    fake_api: FakeApi, client: MapFlights
) -> None:
    fake_api.reply(
        {"code": "out_of_area", "tariff": "home", "message": "outside"}, status=403
    )
    with pytest.raises(MapFlightsOutOfAreaError):
        await client.near(*NEAR)

    fake_api.reply(load_fixture("near.json"))
    start = time.monotonic()
    await client.near(*NEAR)

    assert time.monotonic() - start >= throttle_module.LIVE_INTERVAL_S * 0.9


async def test_rest_requests_do_not_wait(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(load_fixture("near.json"))
    start = time.monotonic()
    await client.near(*NEAR)

    fake_api.reply(load_fixture("airlines.json"))
    await client.airlines()
    await client.airlines()

    assert time.monotonic() - start < throttle_module.LIVE_INTERVAL_S


async def test_clients_with_same_key_share_throttle(
    fake_api: FakeApi, api: tuple[FakeApi, str]
) -> None:
    fake_api.reply(load_fixture("near.json"))

    async with ClientSession() as session:
        first = MapFlights(TEST_KEY, session=session, base_url=api[1])
        second = MapFlights(f" {TEST_KEY} ", session=session, base_url=api[1])
        other = MapFlights("mf_live_ffffffff00", session=session, base_url=api[1])

        await first.near(*NEAR)
        start = time.monotonic()
        await other.near(*NEAR)
        assert time.monotonic() - start < throttle_module.LIVE_INTERVAL_S
        await second.near(*NEAR)
        assert time.monotonic() - start >= throttle_module.LIVE_INTERVAL_S * 0.9


async def test_live_429_blocks_live_only(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(rate_limited("live", 30), status=429, headers={"Retry-After": "30"})
    with pytest.raises(MapFlightsRateLimitError) as exc_info:
        await client.near(*NEAR)
    assert not exc_info.value.local

    with pytest.raises(MapFlightsRateLimitError) as exc_info:
        await client.near(*NEAR)
    assert exc_info.value.local
    assert exc_info.value.scope == "live"
    assert 29 <= (exc_info.value.retry_after or 0) <= 30
    assert len(fake_api.requests) == 1

    fake_api.reply(load_fixture("airlines.json"))
    await client.airlines()
    assert len(fake_api.requests) == 2


async def test_day_429_blocks_rest_only(fake_api: FakeApi, client: MapFlights) -> None:
    fake_api.reply(rate_limited("day", 3600), status=429)
    with pytest.raises(MapFlightsRateLimitError):
        await client.me()

    with pytest.raises(MapFlightsRateLimitError) as exc_info:
        await client.airlines()
    assert exc_info.value.local
    assert exc_info.value.scope == "day"
    assert len(fake_api.requests) == 1

    fake_api.reply(load_fixture("near.json"))
    await client.near(*NEAR)
    assert len(fake_api.requests) == 2


async def test_429_without_scope_blocks_minute(
    fake_api: FakeApi, client: MapFlights
) -> None:
    fake_api.reply(rate_limited(None, 20), status=429)
    with pytest.raises(MapFlightsRateLimitError):
        await client.airlines()

    with pytest.raises(MapFlightsRateLimitError) as exc_info:
        await client.airlines()
    assert exc_info.value.scope == "minute"


async def test_429_without_retry_after_does_not_block(
    fake_api: FakeApi, client: MapFlights
) -> None:
    fake_api.reply({"error": "Too Many Requests"}, status=429)
    with pytest.raises(MapFlightsRateLimitError):
        await client.airlines()

    fake_api.reply(load_fixture("airlines.json"))
    await client.airlines()
    assert len(fake_api.requests) == 2


async def test_minute_limit(
    fake_api: FakeApi, client: MapFlights, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client._throttle, "minute_limit", 3)
    fake_api.reply(load_fixture("near.json"))
    await client.near(*NEAR)

    fake_api.reply(load_fixture("airlines.json"))
    await client.airlines()
    await client.airlines()

    with pytest.raises(MapFlightsRateLimitError) as exc_info:
        await client.airlines()
    assert exc_info.value.local
    assert exc_info.value.scope == "minute"
    assert len(fake_api.requests) == 3

    monkeypatch.setattr(throttle_module, "MINUTE_WINDOW_S", 0.0)
    await client.airlines()
    assert len(fake_api.requests) == 4
