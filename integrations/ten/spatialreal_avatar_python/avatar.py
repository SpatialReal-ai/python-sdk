"""Glue between a TEN audio pipeline and a SpatialReal avatar session in Agora egress mode.

The TEN graph hands this bridge the TTS audio (PCM16, ``sample_rate``); the bridge
streams it to SpatialReal, and the SpatialReal egress worker joins the Agora channel
as ``uid`` and publishes the avatar's audio and animation there.

No TEN imports here so the segment / reconnect logic is unit-testable with a fake
session (see ``tests/``).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

logger = logging.getLogger("spatialreal_avatar")

RECONNECT_BACKOFF_S = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)
SESSION_TOKEN_HOURS = 24


class AvatarSessionLike(Protocol):
    async def init(self) -> None: ...
    async def start(self) -> str: ...
    async def send_audio(self, audio: bytes, end: bool = False) -> str: ...
    async def interrupt(self) -> str: ...
    async def close(self) -> None: ...


SessionFactory = Callable[["BridgeConfig", "AvatarBridge"], AvatarSessionLike]


@dataclass
class BridgeConfig:
    app_id: str
    api_key: str
    avatar_id: str
    environment: str = "us-west"
    console_endpoint: str = ""
    ingress_endpoint: str = ""
    agora_app_id: str = ""
    agora_app_cert: str = ""
    channel_name: str = ""
    avatar_uid: int = 0
    sample_rate: int = 16000
    segment_idle_end_ms: int = 1500

    def validate(self) -> None:
        missing = [
            k for k in ("app_id", "api_key", "avatar_id", "agora_app_id", "channel_name") if not getattr(self, k)
        ]
        if missing:
            raise ValueError(f"spatialreal_avatar_python: missing config {', '.join(missing)}")
        if self.avatar_uid <= 0:
            raise ValueError("spatialreal_avatar_python: agora_avatar_uid must be > 0")
        if self.sample_rate <= 0:
            raise ValueError("spatialreal_avatar_python: input_audio_sample_rate must be > 0")


def agora_token(cfg: BridgeConfig, ttl_s: int = 24 * 3600) -> str:
    """RTC token for the egress worker (publisher role). Without an app certificate the
    App ID itself is the token, as Agora accepts for projects in testing mode."""
    if not cfg.agora_app_cert:
        return cfg.agora_app_id
    from agora_token_builder import RtcTokenBuilder  # pylint: disable=import-error

    return RtcTokenBuilder.buildTokenWithUid(
        cfg.agora_app_id, cfg.agora_app_cert, cfg.channel_name, cfg.avatar_uid, 1, int(time.time()) + ttl_s
    )


def default_session_factory(cfg: BridgeConfig, bridge: AvatarBridge) -> AvatarSessionLike:
    from spatialreal import AgoraEgressConfig, new_avatar_session

    kwargs: dict[str, Any] = dict(
        api_key=cfg.api_key,
        app_id=cfg.app_id,
        avatar_id=cfg.avatar_id,
        expire_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_TOKEN_HOURS),
        sample_rate=cfg.sample_rate,
        environment=cfg.environment,
        agora_egress=AgoraEgressConfig(
            channel_name=cfg.channel_name,
            token=agora_token(cfg),
            uid=cfg.avatar_uid,
            publisher_id=str(cfg.avatar_uid),
        ),
        on_playback=bridge._on_playback,
        on_error=bridge._on_error,
        on_close=bridge._on_close,
    )
    if cfg.console_endpoint:
        kwargs["console_endpoint_url"] = cfg.console_endpoint
    if cfg.ingress_endpoint:
        kwargs["ingress_endpoint_url"] = cfg.ingress_endpoint
    return new_avatar_session(**kwargs)


class AvatarBridge:
    """Owns one SpatialReal session at a time and re-creates it when it drops.

    Segments: audio chunks go out as they arrive; a segment is closed by
    ``end_segment()`` (TEN's ``tts_audio_end`` with reason 1) or, if that never
    comes, ``segment_idle_end_ms`` after the last chunk. ``interrupt()`` drops
    the queue and cuts the avatar off.
    """

    def __init__(
        self,
        cfg: BridgeConfig,
        session_factory: SessionFactory = default_session_factory,
        log: Callable[[str, str], None] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        cfg.validate()
        self.cfg = cfg
        self._factory = session_factory
        self._log = log or (lambda level, msg: getattr(logger, level)(msg))
        self._sleep = sleep
        self._session: AvatarSessionLike | None = None
        self._queue: asyncio.Queue[tuple[bytes, bool] | None] = asyncio.Queue()
        self._sender: asyncio.Task | None = None
        self._reconnect: asyncio.Task | None = None
        self._idle_timer: asyncio.Task | None = None
        self._segment_open = False
        self._closing = False
        self._generation = 0
        self.connected = asyncio.Event()
        self.stats = {"chunks": 0, "segments": 0, "interrupts": 0, "reconnects": 0, "dropped": 0, "playback_ends": 0}

    # ---------------- lifecycle ----------------

    async def connect(self) -> None:
        await self._open_session()
        if self._sender is None:
            self._sender = asyncio.create_task(self._send_loop(), name="spatialreal_avatar_sender")

    async def close(self) -> None:
        self._closing = True
        self._cancel_idle_timer()
        for t in (self._reconnect, self._sender):
            if t is not None:
                t.cancel()
        self._reconnect = self._sender = None
        await self._close_session()

    async def _open_session(self) -> None:
        self._generation += 1
        session = self._factory(self.cfg, self)
        await session.init()
        await session.start()
        self._session = session
        self._segment_open = False
        self.connected.set()
        self._log(
            "info", f"SpatialReal avatar session started (channel={self.cfg.channel_name}, uid={self.cfg.avatar_uid})"
        )

    async def _close_session(self) -> None:
        s, self._session = self._session, None
        self.connected.clear()
        if s is not None:
            try:
                await s.close()
            except Exception as e:  # noqa: BLE001
                self._log("warning", f"close failed: {e}")

    def _schedule_reconnect(self, why: str) -> None:
        if self._closing or (self._reconnect is not None and not self._reconnect.done()):
            return
        self._log("warning", f"SpatialReal session lost ({why}); reconnecting")
        self._reconnect = asyncio.create_task(self._reconnect_loop(), name="spatialreal_avatar_reconnect")

    async def _reconnect_loop(self) -> None:
        await self._close_session()
        self._drain_queue()
        self._segment_open = False
        self._cancel_idle_timer()
        attempt = 0
        while not self._closing:
            delay = RECONNECT_BACKOFF_S[min(attempt, len(RECONNECT_BACKOFF_S) - 1)]
            await self._sleep(delay)
            try:
                await self._open_session()
                self.stats["reconnects"] += 1
                return
            except Exception as e:  # noqa: BLE001
                attempt += 1
                self._log("warning", f"reconnect attempt {attempt} failed: {e}")

    # ---------------- audio in ----------------

    async def push_audio(self, pcm: bytes) -> None:
        if not pcm or self._closing:
            return
        if self._session is None:
            self.stats["dropped"] += 1
            return
        self._queue.put_nowait((pcm, False))

    async def end_segment(self) -> None:
        """Close the current segment (TTS finished). No-op when nothing is open."""
        self._cancel_idle_timer()
        self._queue.put_nowait((b"", True))

    async def interrupt(self) -> None:
        self.stats["interrupts"] += 1
        self._cancel_idle_timer()
        self._drain_queue()
        self._segment_open = False
        s = self._session
        if s is None:
            return
        try:
            await s.interrupt()
        except Exception as e:  # noqa: BLE001
            self._schedule_reconnect(f"interrupt failed: {e}")

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    async def _send_loop(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            pcm, end = item
            s = self._session
            if s is None:
                self.stats["dropped"] += 1
                continue
            if end and not self._segment_open:
                continue
            try:
                await s.send_audio(pcm, end=end)
            except Exception as e:  # noqa: BLE001
                self._schedule_reconnect(f"send failed: {e}")
                continue
            if end:
                self._segment_open = False
                self.stats["segments"] += 1
                self._cancel_idle_timer()
            else:
                self._segment_open = True
                self.stats["chunks"] += 1
                self._arm_idle_timer()

    # ---------------- idle end (fallback when tts_audio_end never comes) ----------------

    def _arm_idle_timer(self) -> None:
        self._cancel_idle_timer()
        if self.cfg.segment_idle_end_ms <= 0:
            return
        self._idle_timer = asyncio.create_task(self._idle_end(self.cfg.segment_idle_end_ms / 1000.0))

    def _cancel_idle_timer(self) -> None:
        t, self._idle_timer = self._idle_timer, None
        if t is not None and not t.done():
            t.cancel()

    async def _idle_end(self, delay: float) -> None:
        try:
            await self._sleep(delay)
        except asyncio.CancelledError:
            return
        if self._segment_open:
            self._log("debug", "segment closed by idle timer")
            self._queue.put_nowait((b"", True))

    # ---------------- session callbacks ----------------

    def _on_playback(self, signal: Any) -> None:
        if getattr(signal, "end", False):
            self.stats["playback_ends"] += 1
            self._log("debug", f"avatar playback ended req_id={getattr(signal, 'req_id', '')}")

    def _on_error(self, err: Exception) -> None:
        self._log("warning", f"SpatialReal session error: {err}")
        if getattr(err, "retryable", True) is False:
            return
        self._schedule_reconnect(f"error: {err}")

    def _on_close(self) -> None:
        if not self._closing:
            self._schedule_reconnect("connection closed")
