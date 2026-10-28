# Changelog

## 0.2.0

First release.

### Added

- `MapFlights` client with an externally owned `aiohttp` session
- Stable endpoints: `near()`, `aircraft_flights()`, `airlines()`
- Experimental endpoints: `me()`, `day_board()`, `flight_by_callsign()`
- `key_prefix()` to get the non-secret key prefix without a request
- Per-key rate limiting shared by all clients of the process: 5 s live
  slot, 60 requests per minute, blocking per 429 scope until `Retry-After`
- `live_rate_limit`, `daily_rate_limit`, `remaining_today` and
  `attribution` from the response headers
- Exceptions for 401, every 403 tariff code, 404 (with
  `MapFlightsNoCurrentFlightError` for `flight_by_callsign`), 429,
  timeouts and network errors
- Typed models (`py.typed`), timestamps as aware UTC `datetime`
