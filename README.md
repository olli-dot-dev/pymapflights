# pymapflights

Asynchronous Python client for the [map.flights](https://map.flights) API.

> **Unofficial.** This library is not made or endorsed by map.flights. It is the
> API layer of the Home Assistant integration
> [ha-mapflights](https://github.com/olli-dot-dev/ha-mapflights).

## Installation

```bash
pip install pymapflights
```

## Usage

```python
import asyncio

from aiohttp import ClientSession

from pymapflights import MapFlights


async def main() -> None:
    async with ClientSession() as session:
        client = MapFlights(
            "YOUR_API_KEY",
            session=session,
            user_agent="my-app/1.0 (+https://example.com)",
        )
        result = await client.near(48.11, 16.57, 25, limit=100)
        print(f"{result.total} aircraft within 25 km")
        for aircraft in result.aircraft:
            print(aircraft.callsign, aircraft.distance_km, aircraft.alt_baro)
        print(client.attribution)


asyncio.run(main())
```

Notes:

- `total` is the number of aircraft in the radius; `aircraft` is capped by
  `limit` (API default 50, max 500). `result.truncated` tells you when the list
  is incomplete.
- When `result.ready` is `False`, a delayed tariff is still filling its buffer
  and the empty list does not mean there is no traffic.
- The session belongs to you; the client never closes it.

## Endpoints

| Method | Endpoint | Stability | Quota |
|---|---|---|---|
| `near(lat, lon, radius_km, limit=)` | `/near/{lat}/{lon}/{radius}` | stable | live (1 per 5 s) |
| `aircraft_flights(hex_id, limit=)` | `/aircraft/{hex}/flights` | stable | daily |
| `airlines(query=, limit=, offset=)` | `/airlines` | stable | daily |
| `me()` | `/me` | experimental | daily |
| `day_board(airport, "arr" \| "dep", day=)` | `/airports/{icao}/day-board` | experimental | daily |
| `flight_by_callsign(callsign)` | `/flights/by-callsign/{callsign}` | experimental | daily |

Experimental endpoints may change within `/api/v1`; their models make every
field optional. `key_prefix(api_key)` returns the non-secret key prefix
(`mf_live_` + 8 hex) without a request.

`flight_by_callsign()` raises `MapFlightsNoCurrentFlightError` when there is
no current flight (`reason` is `no current flight` with `last_flight`, or
`unknown flight`). That is a normal state, but it still counts against the
daily quota. A landing appears there only 20 to 35 minutes after touchdown.

## API keys and terms

Keys are issued by map.flights (operators of a receiving station can create a
free key at <https://map.flights/account/api-key>). Use of the API is subject to
the [map.flights API terms](https://map.flights/api-terms). Attribution is
mandatory: show at least "Data: map.flights"; the full text of the last response
is in `client.attribution`.

### Rate limits

The client enforces the limits per key, shared by every client in the process
that uses the same key:

- **Live** (`near`): one request every 5 s. A call waits for its slot. Every
  call uses the slot, even one that fails (a `near` outside the key's area too).
- **Minute**: at most 60 requests per minute over all endpoints.
- **After a 429** the client remembers `Retry-After` for that scope (`live`,
  `minute` or `day`) and refuses further requests of that scope until then.

A refused request raises `MapFlightsRateLimitError` with `local=True` and is
never sent. `retry_after` and `scope` are set either way.

`client.live_rate_limit` and `client.daily_rate_limit` hold the
`X-RateLimit-*` headers of the last live and the last other response. For live
requests they describe the live bucket, not the daily quota, so
`client.remaining_today` only comes from non-live responses.

## Errors

| Exception | When |
|---|---|
| `MapFlightsAuthError` | 401, unknown or revoked key |
| `MapFlightsOutOfAreaError` | 403 `out_of_area` |
| `MapFlightsKeyDormantError` | 403 `key_dormant` |
| `MapFlightsNotInTariffError` | 403 `group_not_in_tariff`, `endpoint_not_in_tariff`, `format_not_in_tariff` |
| `MapFlightsTariffError` | base class of the 403 errors above, also for unknown codes |
| `MapFlightsNotFoundError` | 404 (parsed body in `body`) |
| `MapFlightsNoCurrentFlightError` | 404 of `flight_by_callsign`, a normal state |
| `MapFlightsRateLimitError` | 429, or refused locally (`local=True`) |
| `MapFlightsConnectionError` | timeout or network error |
| `MapFlightsError` | base class of everything above |

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## License

MIT
