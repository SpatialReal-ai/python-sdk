"""Endpoint resolution: environment presets, the config service, explicit overrides.

Nothing here touches the network — the config service fetch is stubbed, including
the case where it is unreachable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from spatialreal import environments, new_avatar_session  # noqa: E402

pytestmark = pytest.mark.asyncio


def make_session(**kwargs):
    return new_avatar_session(api_key="k", app_id="a", avatar_id="av", **kwargs)


@pytest.fixture(autouse=True)
def _clear_cache():
    environments.reset_cache()
    yield
    environments.reset_cache()


def stub_service(monkeypatch, value):
    async def _fetch():
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(environments, "_fetch", _fetch)


async def test_explicit_urls_win_and_skip_the_service(monkeypatch) -> None:
    """A caller that passes URLs is never overridden — and never waits on a lookup."""

    async def _fail():
        raise AssertionError("config service must not be consulted")

    monkeypatch.setattr(environments, "_fetch", _fail)

    session = make_session(
        console_endpoint_url="https://console.example",
        ingress_endpoint_url="wss://ingress.example/v2/driveningress",
    )
    assert await session._console_endpoint() == "https://console.example"
    assert await session._ingress_endpoint() == "wss://ingress.example/v2/driveningress"
    print("PASS explicit endpoints win over the environment")


async def test_unreachable_service_falls_back_to_the_preset(monkeypatch) -> None:
    """A config lookup that fails must not fail the session."""
    stub_service(monkeypatch, RuntimeError("boom"))

    session = make_session()  # environment defaults to us-west
    assert await session._console_endpoint() == "https://api.spatialreal.cloud"
    assert await session._ingress_endpoint() == "https://driven.us-west.spatialreal.cloud/v2/driveningress"

    # the ws target turns the https origin into wss and appends the socket path
    ws_url, _ = session._build_ws_target(await session._ingress_endpoint())
    assert ws_url.startswith("wss://driven.us-west.spatialreal.cloud/v2/driveningress/websocket")
    print("PASS preset fallback when the config service is unreachable")


async def test_service_value_overrides_the_preset(monkeypatch) -> None:
    """The service is the source of truth: a moved deployment needs no SDK release."""
    stub_service(monkeypatch, {"us-west": {"api": "https://api.moved", "driveningress": "https://driven.moved"}})

    session = make_session()
    assert await session._console_endpoint() == "https://api.moved"
    assert await session._ingress_endpoint() == "https://driven.moved/v2/driveningress"
    print("PASS config service overrides the built-in preset")


async def test_region_known_only_to_the_service(monkeypatch) -> None:
    """A region added server-side works without shipping a new SDK."""
    stub_service(
        monkeypatch,
        {
            "ap-northeast": {
                "api": "https://api.spatialreal.cloud",
                "driveningress": "https://driven.ap-northeast.spatialreal.cloud",
            }
        },
    )

    session = make_session(environment="ap-northeast")
    assert await session._ingress_endpoint() == "https://driven.ap-northeast.spatialreal.cloud/v2/driveningress"
    print("PASS a service-only region resolves without an SDK release")


async def test_unknown_environment_is_an_error(monkeypatch) -> None:
    """A typo'd environment surfaces instead of silently hitting the default."""
    stub_service(monkeypatch, {})

    session = make_session(environment="mars")
    with pytest.raises(ValueError) as exc:
        await session._console_endpoint()
    assert "mars" in str(exc.value)
    print("PASS unknown environment raises")


async def test_internal_deployments_are_not_selectable(monkeypatch) -> None:
    """Only public deployments are nameable; internal ones need explicit URLs."""
    stub_service(monkeypatch, {})

    assert list(environments.BUILTIN_ENVIRONMENTS) == ["us-west"]
    with pytest.raises(ValueError):
        await make_session(environment="test")._console_endpoint()

    # …which is how the test deployment is reached instead
    session = make_session(
        console_endpoint_url="https://api.spatialreal.dev",
        ingress_endpoint_url="wss://test-driven.spatialreal.dev/v2/driveningress",
    )
    assert await session._console_endpoint() == "https://api.spatialreal.dev"
    print("PASS internal deployments are not a selectable environment")
