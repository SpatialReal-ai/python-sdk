"""Protocol-level tests: a real in-process console (aiohttp) and driven-ingress
(websockets) speaking the actual protobuf contract — not hand-wavy mocks."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
import websockets
from aiohttp import web

from spatialreal import (
    AgoraEgressConfig,
    AvatarSDKError,
    AvatarSDKErrorCode,
    CloseCode,
    LiveKitEgressConfig,
    SessionTokenError,
    new_avatar_session,
)
from spatialreal.proto.generated import message_pb2

EXPIRE = datetime.now(timezone.utc) + timedelta(hours=1)


class FakeBackend:
    """Console + driven-ingress in one object.

    ``script`` is a coroutine run per WebSocket connection AFTER the standard
    handshake (recv ClientConfigureSession → send ServerConfirmSession); it gets
    (self, ws) and drives the rest of the exchange.
    """

    def __init__(self):
        self.token_status = 200
        self.token_body: dict | None = None
        self.script = None
        self.received: list[message_pb2.Message] = []
        self.configure: message_pb2.ClientConfigureSession | None = None
        self.ws_headers: dict[str, str] = {}
        self.handshake_reply = None  # None = normal confirm
        self.console_url = ""
        self.token_paths: list[str] = []
        self.ingress_url = ""
        self._servers = []

    async def __aenter__(self):
        app = web.Application()
        app.router.add_post("/v1/auth/session-token", self._token_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.console_url = f"http://127.0.0.1:{port}"
        self._servers.append(runner)

        self._ws_server = await websockets.serve(self._ws_handler, "127.0.0.1", 0)
        ws_port = self._ws_server.sockets[0].getsockname()[1]
        self.ingress_url = f"http://127.0.0.1:{ws_port}"
        return self

    async def __aexit__(self, *exc):
        self._ws_server.close()
        await self._ws_server.wait_closed()
        for runner in self._servers:
            await runner.cleanup()

    async def _token_handler(self, request: web.Request) -> web.Response:
        assert request.headers.get("X-Api-Key"), "missing X-Api-Key"
        self.token_paths.append(request.path)
        body = self.token_body if self.token_body is not None else {"session_token": "tok-123"}
        return web.Response(status=self.token_status, text=json.dumps(body), content_type="application/json")

    async def _ws_handler(self, ws):
        req = getattr(ws, "request", None)
        headers = getattr(req, "headers", None) or getattr(ws, "request_headers", {})
        self.ws_headers = {k.lower(): v for k, v in headers.items()}

        raw = await ws.recv()
        envelope = message_pb2.Message.FromString(raw)
        assert envelope.type == message_pb2.MESSAGE_CLIENT_CONFIGURE_SESSION
        self.configure = envelope.client_configure_session

        if self.handshake_reply is not None:
            await ws.send(self.handshake_reply.SerializeToString())
            return

        confirm = message_pb2.Message()
        confirm.type = message_pb2.MESSAGE_SERVER_CONFIRM_SESSION
        confirm.server_confirm_session.connection_id = "conn-1"
        await ws.send(confirm.SerializeToString())

        if self.script is not None:
            await self.script(self, ws)
        else:
            async for message in ws:
                self.received.append(message_pb2.Message.FromString(message))


def make_session(backend: FakeBackend, **overrides):
    kwargs = dict(
        api_key="k",
        app_id="a",
        avatar_id="av",
        console_endpoint_url=backend.console_url,
        ingress_endpoint_url=backend.ingress_url,
        expire_at=EXPIRE,
        sample_rate=16000,
    )
    kwargs.update(overrides)
    return new_avatar_session(**kwargs)


def anim_msg(req_id: str, end: bool) -> bytes:
    m = message_pb2.Message()
    m.type = message_pb2.MESSAGE_SERVER_RESPONSE_ANIMATION
    m.server_response_animation.req_id = req_id
    m.server_response_animation.end = end
    m.server_response_animation.connection_id = "conn-1"
    return m.SerializeToString()


# --------------------------------------------------------------------- token


async def test_init_exchanges_api_key_for_token():
    async with FakeBackend() as backend:
        session = make_session(backend)
        await session.init()
        assert session._session_token == "tok-123"
        assert backend.token_paths == ["/v1/auth/session-token"], backend.token_paths


async def test_init_maps_auth_failure():
    async with FakeBackend() as backend:
        backend.token_status = 401
        backend.token_body = {"errors": [{"code": "unauthorized", "detail": "bad key", "status": "401"}]}
        session = make_session(backend)
        with pytest.raises(SessionTokenError) as exc:
            await session.init()
        assert exc.value.code == AvatarSDKErrorCode.sessionTokenInvalid
        assert exc.value.http_status == 401
        assert "bad key" in exc.value.message


async def test_init_rejects_bodyless_success():
    async with FakeBackend() as backend:
        backend.token_body = {}
        session = make_session(backend)
        with pytest.raises(SessionTokenError) as exc:
            await session.init()
        assert exc.value.code == AvatarSDKErrorCode.protocolError


# ----------------------------------------------------------------- handshake


async def test_start_handshake_headers_auth_and_egress_config():
    async with FakeBackend() as backend:
        session = make_session(
            backend,
            livekit_egress=LiveKitEgressConfig(
                url="wss://lk.example", api_token="jwt", room_name="room-1", publisher_id="avatar", idle_timeout=30
            ),
        )
        await session.init()
        connection_id = await session.start()
        assert connection_id == "conn-1"
        assert session.connection_id == "conn-1"
        assert session.capabilities == ()
        # header-style auth by default
        assert backend.ws_headers.get("x-app-id") == "a"
        assert backend.ws_headers.get("x-session-key") == "tok-123"
        # egress config made it onto the wire verbatim
        cfg = backend.configure
        assert cfg.egress_type == message_pb2.EGRESS_TYPE_LIVEKIT
        assert cfg.livekit_egress.api_token == "jwt"
        assert cfg.livekit_egress.room_name == "room-1"
        assert cfg.livekit_egress.idle_timeout == 30
        assert cfg.sample_rate == 16000
        await session.close()


async def test_start_agora_egress_config_on_the_wire():
    async with FakeBackend() as backend:
        session = make_session(
            backend,
            agora_egress=AgoraEgressConfig(
                channel_name="ch-1", token="rtc-token", uid=7, publisher_id="7", app_id="appid-1"
            ),
        )
        await session.init()
        await session.start()
        cfg = backend.configure
        assert cfg.egress_type == message_pb2.EGRESS_TYPE_AGORA
        assert cfg.agora_egress.channel_name == "ch-1"
        assert cfg.agora_egress.token == "rtc-token"
        assert cfg.agora_egress.uid == 7
        assert cfg.agora_egress.publisher_id == "7"
        assert cfg.agora_egress.app_id == "appid-1"
        await session.close()


async def test_start_rejected_by_server_error():
    async with FakeBackend() as backend:
        reply = message_pb2.Message()
        reply.type = message_pb2.MESSAGE_SERVER_ERROR
        reply.server_error.code = int(CloseCode.AUTH_FAILED)
        reply.server_error.message = "token expired"
        backend.handshake_reply = reply

        session = make_session(backend)
        await session.init()
        with pytest.raises(AvatarSDKError) as exc:
            await session.start()
        assert exc.value.code == AvatarSDKErrorCode.sessionTokenInvalid
        assert exc.value.retryable is False
        assert session._connection is None  # cleaned up


# --------------------------------------------------------------- audio + ids


async def test_send_audio_req_id_lifecycle_and_interrupt():
    async with FakeBackend() as backend:
        session = make_session(backend)
        await session.init()
        await session.start()

        r1 = await session.send_audio(b"\x01\x02")
        r1b = await session.send_audio(b"\x03", end=False)
        assert r1 == r1b, "same segment keeps one req_id"
        r1c = await session.send_audio(b"", end=True)
        assert r1c == r1

        r2 = await session.send_audio(b"\x04")
        assert r2 != r1, "new segment gets a fresh req_id"

        interrupted = await session.interrupt()
        assert interrupted == r2, "interrupt targets the most recent request"
        r3 = await session.send_audio(b"\x05")
        assert r3 not in (r1, r2), "req_ids are never reused"

        await asyncio.sleep(0.1)
        await session.close()

        kinds = [m.type for m in backend.received]
        assert kinds.count(message_pb2.MESSAGE_CLIENT_AUDIO_INPUT) == 5
        assert kinds.count(message_pb2.MESSAGE_CLIENT_INTERRUPT) == 1
        audio_msgs = [
            m.client_audio_input for m in backend.received if m.type == message_pb2.MESSAGE_CLIENT_AUDIO_INPUT
        ]
        assert audio_msgs[0].audio == b"\x01\x02"
        assert audio_msgs[2].end is True


async def test_interrupt_works_after_segment_end():
    async with FakeBackend() as backend:
        session = make_session(backend)
        await session.init()
        await session.start()
        req = await session.send_audio(b"\x01", end=True)
        assert await session.interrupt() == req
        await session.close()


# ----------------------------------------------------------------- callbacks


async def test_playback_callbacks_structured_and_raw():
    got_signals = []
    got_frames = []

    async def script(backend, ws):
        await ws.send(anim_msg("req-A", end=False))
        await ws.send(anim_msg("req-A", end=True))
        await asyncio.sleep(0.2)

    async with FakeBackend() as backend:
        backend.script = script
        session = make_session(
            backend,
            on_playback=got_signals.append,
            transport_frames=lambda frame, is_last: got_frames.append((len(frame), is_last)),
        )
        await session.init()
        await session.start()
        await asyncio.sleep(0.3)
        await session.close()

    assert [(s.req_id, s.end) for s in got_signals] == [("req-A", False), ("req-A", True)]
    assert got_signals[0].has_animation is False
    assert got_signals[0].connection_id == "conn-1"
    assert [last for _, last in got_frames] == [False, True]


async def test_unknown_message_types_are_ignored():
    errors = []

    async def script(backend, ws):
        m = message_pb2.Message()
        m.type = 99  # a future message type
        await ws.send(m.SerializeToString())
        await ws.send(anim_msg("req-B", end=True))
        await asyncio.sleep(0.2)

    async with FakeBackend() as backend:
        backend.script = script
        signals = []
        session = make_session(backend, on_playback=signals.append, on_error=errors.append)
        await session.init()
        await session.start()
        await asyncio.sleep(0.3)
        await session.close()

    assert errors == []
    assert [s.req_id for s in signals] == ["req-B"]


# ---------------------------------------------------------- close semantics


async def test_server_close_code_reaches_on_error_with_retryability():
    errors = []
    closes = []

    async def script(backend, ws):
        await ws.close(code=int(CloseCode.UPSTREAM_UNAVAILABLE), reason="rolling deploy")

    async with FakeBackend() as backend:
        backend.script = script
        session = make_session(backend, on_error=errors.append, on_close=lambda: closes.append(1))
        await session.init()
        await session.start()
        await asyncio.sleep(0.3)
        await session.close()

    assert len(errors) == 1
    err = errors[0]
    assert err.close_code == int(CloseCode.UPSTREAM_UNAVAILABLE)
    assert err.code == AvatarSDKErrorCode.upstreamError
    assert err.retryable is True
    assert closes == [1], "on_close fires exactly once even with close() after the drop"


async def test_auth_close_code_is_not_retryable():
    errors = []

    async def script(backend, ws):
        await ws.close(code=int(CloseCode.AUTH_FAILED), reason="bad token")

    async with FakeBackend() as backend:
        backend.script = script
        session = make_session(backend, on_error=errors.append)
        await session.init()
        await session.start()
        await asyncio.sleep(0.3)
        await session.close()

    assert errors[0].retryable is False
    assert errors[0].code == AvatarSDKErrorCode.sessionTokenInvalid


async def test_close_is_idempotent_and_send_after_close_raises():
    closes = []
    async with FakeBackend() as backend:
        session = make_session(backend, on_close=lambda: closes.append(1))
        await session.init()
        await session.start()
        await session.close()
        await session.close()
        assert closes == [1]
        with pytest.raises(ValueError):
            await session.send_audio(b"\x00")


# ------------------------------------------------------------------- misc


async def test_new_avatar_session_rejects_unknown_kwargs():
    with pytest.raises(TypeError) as exc:
        new_avatar_session(api_key="k", not_a_real_option=1)
    assert "not_a_real_option" in str(exc.value)


async def test_query_auth_mode_puts_credentials_in_url():
    async with FakeBackend() as backend:
        session = make_session(backend, use_query_auth=True)
        await session.init()
        await session.start()
        # header-style credentials absent; server saw them via query (implied by
        # a successful handshake — the fake accepts either, so assert absence)
        assert "x-app-id" not in backend.ws_headers
        await session.close()


async def test_server_error_with_grpc_code_is_not_a_close_code():
    errors = []

    async def script(backend, ws):
        m = message_pb2.Message()
        m.type = message_pb2.MESSAGE_SERVER_ERROR
        m.server_error.code = 14  # gRPC Unavailable relayed from an upstream
        m.server_error.message = "inference server Animate failed"
        await ws.send(m.SerializeToString())
        await asyncio.sleep(0.2)

    async with FakeBackend() as backend:
        backend.script = script
        session = make_session(backend, on_error=errors.append)
        await session.init()
        await session.start()
        await asyncio.sleep(0.3)
        await session.close()

    err = errors[0]
    assert err.close_code is None, "gRPC codes must not enter the close-code contract"
    assert err.code == AvatarSDKErrorCode.serverError
    assert err.server_code == "14"


def test_session_token_endpoint_uses_auth_route() -> None:
    """cp's primary route is /v1/auth/session-token; the old /v1/console suffix a
    caller may still carry in console_endpoint_url is normalized away, never doubled."""
    from spatialreal.session import _session_token_endpoint

    root = "https://api.spatialreal.dev"
    assert _session_token_endpoint(root) == f"{root}/v1/auth/session-token"
    assert _session_token_endpoint(root + "/") == f"{root}/v1/auth/session-token"
    assert _session_token_endpoint(root + "/v1/console") == f"{root}/v1/auth/session-token"
    assert _session_token_endpoint(root + "/v1/console/") == f"{root}/v1/auth/session-token"


def playback_state_msg(req_id, state, played_ms=0, reason=""):
    m = message_pb2.Message()
    m.type = message_pb2.MESSAGE_SERVER_PLAYBACK_STATE
    m.server_playback_state.req_id = req_id
    m.server_playback_state.state = state
    m.server_playback_state.played_ms = played_ms
    m.server_playback_state.reason = reason
    m.server_playback_state.connection_id = "conn-1"
    return m.SerializeToString()


async def test_pause_resume_send_control_messages_without_clearing_segment():
    async with FakeBackend() as backend:
        session = make_session(backend)
        await session.init()
        await session.start()

        req = await session.send_audio(b"\x01\x02")
        assert await session.pause() == req
        # audio keeps flowing to the same segment while paused
        assert await session.send_audio(b"\x03") == req
        assert await session.resume() == req
        assert await session.send_audio(b"", end=True) == req

        await asyncio.sleep(0.1)
        await session.close()

        kinds = [m.type for m in backend.received]
        assert kinds.count(message_pb2.MESSAGE_CLIENT_PAUSE) == 1
        assert kinds.count(message_pb2.MESSAGE_CLIENT_RESUME) == 1
        pauses = [m.client_pause for m in backend.received if m.type == message_pb2.MESSAGE_CLIENT_PAUSE]
        assert pauses[0].req_id == req


async def test_pause_before_any_audio_raises():
    async with FakeBackend() as backend:
        session = make_session(backend)
        await session.init()
        await session.start()
        with pytest.raises(ValueError):
            await session.pause()
        await session.close()


async def test_playback_state_events_parsed():
    from spatialreal import InterruptReason, PlaybackState

    events = []

    async def script(backend, ws):
        await ws.send(playback_state_msg("req-A", message_pb2.ServerPlaybackState.PAUSED, 1200))
        await ws.send(playback_state_msg("req-A", message_pb2.ServerPlaybackState.PLAYING, 1200))
        await ws.send(
            playback_state_msg("req-A", message_pb2.ServerPlaybackState.INTERRUPTED, 1500, reason="pause_timeout")
        )
        await asyncio.sleep(0.2)

    async with FakeBackend() as backend:
        backend.script = script
        session = make_session(backend, on_playback_state=events.append)
        await session.init()
        await session.start()
        await asyncio.sleep(0.3)
        await session.close()

    assert [(e.state, e.played_ms) for e in events] == [
        (PlaybackState.PAUSED, 1200),
        (PlaybackState.PLAYING, 1200),
        (PlaybackState.INTERRUPTED, 1500),
    ]
    assert events[2].reason == InterruptReason.PAUSE_TIMEOUT
    assert events[0].req_id == "req-A"


async def test_playback_state_ignored_without_callback():
    async def script(backend, ws):
        await ws.send(playback_state_msg("req-A", message_pb2.ServerPlaybackState.PAUSED))
        await ws.send(anim_msg("req-A", end=True))
        await asyncio.sleep(0.2)

    async with FakeBackend() as backend:
        backend.script = script
        signals, errors = [], []
        session = make_session(backend, on_playback=signals.append, on_error=errors.append)
        await session.init()
        await session.start()
        await asyncio.sleep(0.3)
        await session.close()

    # no on_playback_state handler: the message is silently ignored, others still flow
    assert errors == []
    assert [s.req_id for s in signals] == ["req-A"]
