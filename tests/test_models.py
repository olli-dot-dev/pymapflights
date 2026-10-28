"""Tests for the models."""

from datetime import UTC, datetime

from pymapflights import NearResponse

from .conftest import load_fixture


def test_near_roundtrip() -> None:
    result = NearResponse.from_dict(load_fixture("near.json"))

    data = result.to_dict()

    assert data["now"] == 1793188800000
    assert data["ac"][0]["distanceKm"] == 4.21
    assert NearResponse.from_dict(data) == result
    assert result.now == datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
