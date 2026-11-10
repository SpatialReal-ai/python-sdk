"""Negotiate the actual Agora source writer before any audio is allowed."""

import asyncio

import pytest
import websockets

from spatialreal import AgoraEgressConfig, AvatarSDKError, CloseCode, UnsupportedConfigurationError
from spatialreal.proto.generated import message_pb2
from tests.test_session import FakeBackend, make_session

CAPABILITIES = ["agora_source_timeline_only", "agora_source_burst_v1"]


@pytest.mark.parametrize("explicit", [False, True])
async def test_explicit_legacy_zero_omitted_on_wire(explicit):
    async with FakeBackend() as backend:
        options = {"source_timeline_only": False, **({"source_playback_profile": 0} if explicit else {})}
        session = make_session(backend, agora_egress=AgoraEgressConfig(**options))
        await session.init()
        await session.start()
        assert "source_playback_profile" not in {field.name for field, _ in backend.configure.agora_egress.ListFields()}
        assert session.capabilities == ()
        await session.close()


@pytest.mark.parametrize("explicit", [False, True])
async def test_burst_default_and_explicit_profile_require_actual_dual_ack(explicit):
    from spatialreal import RtcSourcePlaybackProfile

    async with FakeBackend() as backend:
        backend.capabilities = CAPABILITIES
        config = AgoraEgressConfig(**({"source_timeline_only": True, "source_playback_profile": 1} if explicit else {}))
        assert config.source_playback_profile is RtcSourcePlaybackProfile.BOUNDED_BURST_V1
        session = make_session(backend, agora_egress=config)
        await session.init()
        await session.start()
        wire = backend.configure.agora_egress
        assert wire.source_playback_profile == message_pb2.RTC_SOURCE_PLAYBACK_PROFILE_BOUNDED_BURST_V1
        assert wire.DESCRIPTOR.fields_by_name["source_playback_profile"].number == 7
        assert set(session.capabilities) == set(CAPABILITIES)
        with pytest.raises(AttributeError):
            session.capabilities = ()
        await session.send_audio(b"\x01\x02", end=True)
        await session.close()


@pytest.mark.parametrize("capabilities", [[], CAPABILITIES[:1], CAPABILITIES[1:], ["playback_control"]])
@pytest.mark.parametrize("explicit", [False, True])
async def test_burst_missing_ack_closes_before_read_loop_or_audio(capabilities, explicit):
    async with FakeBackend() as backend:
        backend.capabilities = capabilities
        closed = asyncio.Event()

        async def observe_close(_backend, ws):
            await ws.wait_closed()
            closed.set()

        backend.script = observe_close
        session = make_session(
            backend,
            agora_egress=AgoraEgressConfig(
                **({"source_timeline_only": True, "source_playback_profile": 1} if explicit else {})
            ),
        )
        await session.init()
        with pytest.raises(UnsupportedConfigurationError) as caught:
            await session.start()
        assert not caught.value.retryable
        await asyncio.wait_for(closed.wait(), 1)
        assert session._connection is None
        assert session._read_task is None
        with pytest.raises(ValueError):
            await session.send_audio(b"\x01\x02")
        assert backend.received == []


@pytest.mark.parametrize("value", [True, False, -1, 2, 999, "1", 1.0, {}, []])
def test_burst_rejects_unknown_or_untyped_profile(value):
    with pytest.raises(ValueError, match="source_playback_profile"):
        AgoraEgressConfig(source_timeline_only=True, source_playback_profile=value)


def test_burst_requires_source_timeline_only():
    with pytest.raises(ValueError, match="source_timeline_only"):
        AgoraEgressConfig(source_timeline_only=False, source_playback_profile=1)


@pytest.mark.parametrize("close_code, retryable", [(1008, False), (int(CloseCode.UPSTREAM_UNAVAILABLE), True)])
async def test_burst_policy_refusal_and_transient_failure_keep_distinct_fates(close_code, retryable):
    async with FakeBackend() as backend:

        async def refuse(ws):
            configure = message_pb2.Message.FromString(await ws.recv()).client_configure_session
            assert configure.agora_egress.source_playback_profile == 1
            error = message_pb2.Message(type=message_pb2.MESSAGE_SERVER_ERROR)
            error.server_error.code = 0 if close_code == 1008 else close_code
            await ws.send(error.SerializeToString())
            await ws.close(code=close_code, reason="test refusal")

        backend._ws_server.close()
        await backend._ws_server.wait_closed()
        backend._ws_server = await websockets.serve(refuse, "127.0.0.1", 0)
        backend.ingress_url = f"http://127.0.0.1:{backend._ws_server.sockets[0].getsockname()[1]}"
        session = make_session(
            backend, agora_egress=AgoraEgressConfig(source_timeline_only=True, source_playback_profile=1)
        )
        await session.init()
        with pytest.raises(AvatarSDKError) as caught:
            await session.start()
        assert caught.value.close_code == close_code
        assert caught.value.retryable is retryable
        assert session._connection is None
        assert session._read_task is None
