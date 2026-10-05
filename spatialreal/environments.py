"""Where a deployment lives, and how the SDK finds it.

Callers name an environment (``us-west``) instead of writing URLs, so adding a
region or moving a deployment is a config-service change rather than an SDK
release. The built-in presets below are only a fallback for when that service
cannot be reached — they are a copy, not the source of truth.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import aiohttp

CONFIG_SERVICE_URL = "https://config.spatialreal.cloud/sdk"
# The session must not hang on a config lookup; the presets cover the timeout.
CONFIG_SERVICE_TIMEOUT = 3.0
DEFAULT_ENVIRONMENT = "us-west"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnvironmentEndpoints:
    """Origins for one environment; the SDK appends the routes itself."""

    # OpenAPI root — where session tokens come from.
    api: str
    # driven-ingress origin, without the /v2/driveningress path.
    driveningress: str


# Public deployments only. Internal ones are reached by passing console_endpoint_url /
# ingress_endpoint_url explicitly, so naming them here cannot expose them to callers.
BUILTIN_ENVIRONMENTS: dict[str, EnvironmentEndpoints] = {
    "us-west": EnvironmentEndpoints(
        api="https://api.spatialreal.cloud",
        driveningress="https://driven.us-west.spatialreal.cloud",
    ),
}

# Fetched once per process: every session in it resolves against the same answer.
_cache: dict[str, dict[str, str]] | None = None
_lock = asyncio.Lock()


def reset_cache() -> None:
    """Forget the fetched config (tests, or a long-lived process that must re-read)."""
    global _cache
    _cache = None


async def _fetch() -> dict[str, dict[str, str]]:
    """The config service's environments, or {} if it cannot be read."""
    timeout = aiohttp.ClientTimeout(total=CONFIG_SERVICE_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(CONFIG_SERVICE_URL) as response:
            if response.status != 200:
                raise RuntimeError(f"config service returned {response.status}")
            body = await response.json(content_type=None)
    environments = body.get("environments") if isinstance(body, dict) else None
    return environments if isinstance(environments, dict) else {}


async def resolve(environment: str) -> EnvironmentEndpoints:
    """Endpoints for ``environment``: the config service's, else the built-in preset.

    Raises ValueError when neither knows the name, since a wrong environment is a
    caller mistake worth surfacing rather than silently defaulting elsewhere.
    """
    global _cache

    if _cache is None:
        async with _lock:
            if _cache is None:
                try:
                    _cache = await _fetch()
                except Exception as e:
                    # Not fatal: the presets are exactly what this service would serve
                    # today; a session should not fail because config lookup did.
                    logger.debug("SpatialReal config service unavailable (%s); using presets", e)
                    _cache = {}

    preset = BUILTIN_ENVIRONMENTS.get(environment)
    remote = _cache.get(environment) or {}
    if not preset and not remote:
        known = sorted(set(BUILTIN_ENVIRONMENTS) | set(_cache))
        raise ValueError(f"Unknown environment {environment!r}; known environments: {known}")

    return EnvironmentEndpoints(
        api=remote.get("api") or (preset.api if preset else ""),
        driveningress=remote.get("driveningress") or (preset.driveningress if preset else ""),
    )
