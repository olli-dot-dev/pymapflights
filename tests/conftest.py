"""Fixtures for pymapflights tests."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

from pymapflights import MapFlights, throttle

TEST_KEY = "mf_live_0123abcd" + "ef" * 24

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture."""
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return data


@dataclass
class FakeApi:
    """Local HTTP server that answers every request with the configured reply."""

    status: int = 200
    payload: object = field(default_factory=dict)
    text: str | None = None
    content_type: str = "text/plain"
    headers: dict[str, str] | None = None
    requests: list[web.Request] = field(default_factory=list)
    delay: float = 0

    def reply(
        self,
        payload: object = None,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        text: str | None = None,
        content_type: str = "text/plain",
    ) -> None:
        """Set the reply for the following requests."""
        self.payload = payload
        self.status = status
        self.headers = headers
        self.text = text
        self.content_type = content_type

    async def handle(self, request: web.Request) -> web.StreamResponse:
        """Record the request and answer it (a response can only be sent once)."""
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.text is not None:
            return web.Response(
                status=self.status,
                text=self.text,
                headers=self.headers,
                content_type=self.content_type,
            )
        return web.json_response(self.payload, status=self.status, headers=self.headers)

    @property
    def last(self) -> web.Request:
        """The most recent request."""
        return self.requests[-1]


@pytest.fixture(autouse=True)
def fast_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fresh throttles per test with a short live interval."""
    monkeypatch.setattr(throttle, "LIVE_INTERVAL_S", 0.05)
    monkeypatch.setattr(throttle, "_throttles", {})


@pytest.fixture
async def api() -> AsyncIterator[tuple[FakeApi, str]]:
    """Fake API and its base URL."""
    fake = FakeApi()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", fake.handle)
    server = TestServer(app)
    await server.start_server()
    try:
        yield fake, str(server.make_url(""))
    finally:
        await server.close()


@pytest.fixture
def fake_api(api: tuple[FakeApi, str]) -> FakeApi:
    """The fake API."""
    return api[0]


@pytest.fixture
async def client(api: tuple[FakeApi, str]) -> AsyncIterator[MapFlights]:
    """Client talking to the fake API."""
    async with ClientSession() as session:
        yield MapFlights(
            TEST_KEY,
            session=session,
            user_agent="test-agent/1.0",
            base_url=api[1],
        )
