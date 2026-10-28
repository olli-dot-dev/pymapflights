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

## API keys and terms

Keys are issued by map.flights (operators of a receiving station can create a
free key at <https://map.flights/account/api-key>). Use of the API is subject to
the [map.flights API terms](https://map.flights/api-terms). Attribution is
mandatory: show at least "Data: map.flights"; the full text of the last response
is in `client.attribution`.

Rate limits are enforced by the server. `client.rate_limit` holds the
`X-RateLimit-*` headers of the last response, and `MapFlightsRateLimitError`
carries `retry_after` and `scope` (`live`, `minute` or `day`).

## Errors

| Exception | When |
|---|---|
| `MapFlightsAuthError` | 401, unknown or revoked key |
| `MapFlightsOutOfAreaError` | 403 `out_of_area` |
| `MapFlightsKeyDormantError` | 403 `key_dormant` |
| `MapFlightsNotInTariffError` | 403 `group_not_in_tariff`, `endpoint_not_in_tariff`, `format_not_in_tariff` |
| `MapFlightsTariffError` | base class of the 403 errors above, also for unknown codes |
| `MapFlightsNotFoundError` | 404 |
| `MapFlightsRateLimitError` | 429 |
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
