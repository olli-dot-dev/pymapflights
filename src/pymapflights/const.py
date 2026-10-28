"""Constants for the map.flights API client."""

from typing import Final

VERSION: Final = "0.1.0"

DEFAULT_BASE_URL: Final = "https://map.flights"
DEFAULT_USER_AGENT: Final = (
    f"pymapflights/{VERSION} (+https://github.com/olli-dot-dev/pymapflights)"
)
DEFAULT_TIMEOUT: Final = 10.0

HEADER_API_KEY: Final = "x-api-key"
HEADER_ATTRIBUTION: Final = "x-data-attribution"
HEADER_RETRY_AFTER: Final = "Retry-After"
HEADER_RATE_LIMIT: Final = "X-RateLimit-Limit"
HEADER_RATE_REMAINING: Final = "X-RateLimit-Remaining"
HEADER_RATE_RESET: Final = "X-RateLimit-Reset"

NEAR_MAX_RADIUS_KM: Final = 500
NEAR_MAX_LIMIT: Final = 500
