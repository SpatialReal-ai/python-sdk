"""AvatarBridge against a fake session: segments, idle end, flush, reconnect.
Runs without the TEN runtime (``avatar.py`` has no TEN imports)."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spatialreal_avatar_python"))
from avatar import AvatarBridge, BridgeConfig, agora_token  # noqa: E402


def cfg(**over) -> BridgeConfig:
    base = dict(
        app_id="app",
        api_key="key",
        avatar_id="av",
        agora_app_id="aid",
        channel_name="ch",
        avatar_uid=7,
        sample_rate=16000,
        segment_idle_end_ms=50,
    )
    base.update(over)
    return BridgeConfig(**base)


class FakeSession:
    instances: list[FakeSession] = []

    def __init__(self, fail_sends: int = 0):
        self.calls: list[tuple] = []
        self.fail_sends = fail_sends
        self.closed = False
        FakeSession.instances.append(self)

    async def init(self):
        self.calls.append(("init",))

    async def start(self):
        self.calls.append(("start",))
        return "conn"

    async def send_audio(self, audio: bytes, end: bool = False):
        if self.fail_sends > 0:
            self.fail_sends -= 1
            raise RuntimeError("socket gone")
        self.calls.append(("send", audio, end))
        return "req"

    async def interrupt(self):
        self.calls.append(("interrupt",))
        return "req"

    async def close(self):
        self.closed = True


async def settle():
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def _reset():
    FakeSession.instances.clear()


async def test_audio_streams_and_tts_end_closes_segment():
    b = AvatarBridge(cfg(segment_idle_end_ms=0), session_factory=lambda c, br: FakeSession())
    await b.connect()
    s = FakeSession.instances[0]
    await b.push_audio(b"\x01\x02")
    await b.push_audio(b"\x03\x04")
    await settle()
    await b.end_segment()
    await settle()
    assert s.calls[2:] == [("send", b"\x01\x02", False), ("send", b"\x03\x04", False), ("send", b"", True)]
    assert b.stats["segments"] == 1
    # a second end without audio is a no-op
    await b.end_segment()
    await settle()
    assert len(s.calls) == 5
    await b.close()
    assert s.closed


async def test_idle_timer_closes_segment_when_tts_end_never_comes():
    b = AvatarBridge(cfg(segment_idle_end_ms=20), session_factory=lambda c, br: FakeSession())
    await b.connect()
    s = FakeSession.instances[0]
    await b.push_audio(b"\x01\x02")
    await settle()
    await asyncio.sleep(0.08)
    await settle()
    assert s.calls[-1] == ("send", b"", True)
    await b.close()


async def test_flush_drops_queue_and_interrupts():
    b = AvatarBridge(cfg(segment_idle_end_ms=0), session_factory=lambda c, br: FakeSession())
    await b.connect()
    s = FakeSession.instances[0]
    await b.push_audio(b"\x01\x02")
    await settle()
    b._queue.put_nowait((b"\x09\x09", False))  # still queued when the flush lands
    await b.interrupt()
    await settle()
    assert ("interrupt",) in s.calls
    assert ("send", b"\x09\x09", False) not in s.calls
    await b.close()


async def test_send_failure_reconnects_with_a_fresh_session():
    slept: list[float] = []

    async def fake_sleep(d):
        slept.append(d)

    b = AvatarBridge(
        cfg(segment_idle_end_ms=0),
        session_factory=lambda c, br: FakeSession(fail_sends=1 if not FakeSession.instances else 0),
        sleep=fake_sleep,
    )
    await b.connect()
    first = FakeSession.instances[0]
    await b.push_audio(b"\x01\x02")
    await settle()
    await settle()
    assert first.closed
    assert len(FakeSession.instances) == 2
    assert b.stats["reconnects"] == 1
    assert slept == [1.0]
    second = FakeSession.instances[1]
    await b.push_audio(b"\x05\x06")
    await settle()
    assert ("send", b"\x05\x06", False) in second.calls
    await b.close()


async def test_connection_close_callback_reconnects():
    async def fake_sleep(_):
        pass

    b = AvatarBridge(cfg(segment_idle_end_ms=0), session_factory=lambda c, br: FakeSession(), sleep=fake_sleep)
    await b.connect()
    b._on_close()
    await settle()
    await settle()
    assert len(FakeSession.instances) == 2
    await b.close()
    # after close() nothing reconnects
    b._on_close()
    await settle()
    assert len(FakeSession.instances) == 2


def test_config_validation_and_token():
    with pytest.raises(ValueError):
        BridgeConfig(app_id="", api_key="k", avatar_id="a", agora_app_id="x", channel_name="c", avatar_uid=1).validate()
    with pytest.raises(ValueError):
        cfg(avatar_uid=0).validate()
    assert agora_token(cfg()) == "aid"  # no certificate: the App ID is the token
