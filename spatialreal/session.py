"""AvatarSession — one realtime avatar session over the driven-ingress WebSocket.

Lifecycle: ``init()`` exchanges the API key for a session token (console API),
``start()`` opens the WebSocket and performs the v2 handshake
(ClientConfigureSession → ServerConfirmSession), then audio flows via
``send_audio()`` and lifecycle signals arrive on the configured callbacks.
A session object is single-use: after ``close()`` (or a dropped connection),
create a new one — internal request state is deliberately not reusable, so a
fresh connection can never be correlated with a previous connection's requests.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import aiohttp
import websockets

from .config import AudioFormat, SessionConfig
from .errors import (
    AvatarSDKError,
    AvatarSDKErrorCode,
    SessionTokenError,
    error_code_for_close_code,
)
from .events import PlaybackSignal
from .logid import generate_log_id
from .proto.generated import message_pb2

# cp's primary route. `/v1/console/session-tokens` is only an alias kept so older
# callers don't 404; it is the same handler and may go away.
SESSION_TOKEN_PATH = "/v1/auth/session-token"
# Accepted for back-compat: callers used to pass the cp root with this suffix already on it.
LEGACY_CONSOLE_SUFFIX = "/v1/console"
INGRESS_WEBSOCKET_PATH = "/websocket"

logger = logging.getLogger(__name__)


class AvatarSession:
    """Manages one avatar session: token, WebSocket, audio out, lifecycle in."""

    def __init__(self, config: SessionConfig):
        self._config = config
        self._session_token: str | None = None
        self._connection: Any | None = None
        self._connection_id: str | None = None
        self._capabilities: tuple[str, ...] = ()
        self._current_req_id: str | None = None
        self._last_req_id: str | None = None
        self._read_task: asyncio.Task | None = None
        self._close_notified = False

    # ------------------------------------------------------------------ props

    @property
    def config(self) -> SessionConfig:
        return self._config

    @property
    def connection_id(self) -> str | None:
        """Server-assigned connection id (available after ``start()``)."""
        return self._connection_id

    @property
    def capabilities(self) -> tuple[str, ...]:
        """Capability strings the server declared at handshake.

        Empty on servers that don't declare any (the field is a forward-looking
        part of the protocol); callers should feature-detect, not version-detect.
        """
        return self._capabilities

    # ------------------------------------------------------------------ init

    async def init(self) -> None:
        """Exchange the API key for a session token via the console API."""
        if not self._config.api_key:
            raise ValueError("Missing API key")
        if not self._config.console_endpoint_url:
            raise ValueError("Missing console endpoint URL")
        if not self._config.expire_at:
            raise ValueError("Missing expire_at")

        endpoint = _session_token_endpoint(self._config.console_endpoint_url)
        payload = {"expireAt": int(self._config.expire_at.timestamp())}
        headers = {"X-Api-Key": self._config.api_key, "Content-Type": "application/json"}
        timeout = aiohttp.ClientTimeout(total=self._config.token_request_timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(endpoint, json=payload, headers=headers) as response:
                    status = response.status
                    body = await response.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                raise SessionTokenError(
                    f"Failed to create session token: {e}",
                    code=AvatarSDKErrorCode.connectionFailed,
                ) from e

        data = _try_parse_json(body)
        if status != 200 or (isinstance(data, dict) and data.get("errors")):
            raise _session_token_error(status, data, body)
        if not isinstance(data, dict) or not data.get("session_token"):
            raise SessionTokenError(
                "Failed to decode session token response",
                code=AvatarSDKErrorCode.protocolError,
                raw_body=body,
            )
        self._session_token = data["session_token"]

    # ----------------------------------------------------------------- start

    async def start(self) -> str:
        """Open the WebSocket, perform the handshake, start the read loop.

        Returns the server-assigned connection id.
        """
        if self._connection is not None:
            raise ValueError("Session already started")
        if not self._session_token:
            raise ValueError("Session not initialized (call init() first)")
        if not self._config.ingress_endpoint_url:
            raise ValueError("Missing ingress endpoint URL")
        if not self._config.avatar_id:
            raise ValueError("Missing avatar ID")
        if not self._config.app_id:
            raise ValueError("Missing app ID")
        if self._config.livekit_egress is not None and self._config.agora_egress is not None:
            raise ValueError("Cannot configure both livekit_egress and agora_egress")

        ws_url, headers = self._build_ws_target()

        try:
            self._connection = await _ws_connect(ws_url, headers)
        except Exception as e:
            raise _ws_connect_error(e) from e

        try:
            await self._send_configure_session()
            self._connection_id = await self._await_confirm_session()
        except Exception:
            conn, self._connection = self._connection, None
            if conn is not None:
                try:
                    await conn.close()
                except Exception:
                    pass
            raise

        self._read_task = asyncio.create_task(self._read_loop())
        return self._connection_id

    def _build_ws_target(self) -> tuple[str, dict[str, str]]:
        endpoint = self._config.ingress_endpoint_url.rstrip("/") + INGRESS_WEBSOCKET_PATH
        parsed = urlparse(endpoint)
        scheme = parsed.scheme.lower()
        ws_scheme = {"http": "ws", "https": "wss", "ws": "ws", "wss": "wss"}.get(scheme)
        if ws_scheme is None:
            raise ValueError(f"Unsupported ingress endpoint scheme: {scheme!r}")

        query = parse_qs(parsed.query)
        query["id"] = [self._config.avatar_id]
        headers: dict[str, str] = {}
        if self._config.use_query_auth:
            query["appId"] = [self._config.app_id]
            query["sessionKey"] = [self._session_token or ""]
        else:
            headers = {"X-App-ID": self._config.app_id, "X-Session-Key": self._session_token or ""}

        return (
            urlunparse((ws_scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query, doseq=True), "")),
            headers,
        )

    async def _send_configure_session(self) -> None:
        cfg = self._config
        msg = message_pb2.Message()
        msg.type = message_pb2.MESSAGE_CLIENT_CONFIGURE_SESSION
        s = msg.client_configure_session
        s.sample_rate = int(cfg.sample_rate)
        s.bitrate = int(cfg.bitrate)
        s.audio_format = (
            message_pb2.AUDIO_FORMAT_OGG_OPUS
            if cfg.audio_format == AudioFormat.OGG_OPUS
            else message_pb2.AUDIO_FORMAT_PCM_S16LE
        )
        s.transport_compression = message_pb2.TRANSPORT_COMPRESSION_NONE

        if cfg.livekit_egress is not None:
            lk = cfg.livekit_egress
            s.egress_type = message_pb2.EGRESS_TYPE_LIVEKIT
            s.livekit_egress.url = lk.url
            s.livekit_egress.api_token = lk.api_token
            s.livekit_egress.api_key = lk.api_key
            s.livekit_egress.api_secret = lk.api_secret
            s.livekit_egress.room_name = lk.room_name
            s.livekit_egress.publisher_id = lk.publisher_id
            if lk.extra_attributes:
                s.livekit_egress.extra_attributes.update(lk.extra_attributes)
            s.livekit_egress.idle_timeout = int(lk.idle_timeout)
        elif cfg.agora_egress is not None:
            ag = cfg.agora_egress
            s.egress_type = message_pb2.EGRESS_TYPE_AGORA
            s.agora_egress.channel_name = ag.channel_name
            s.agora_egress.token = ag.token
            s.agora_egress.uid = ag.uid
            s.agora_egress.publisher_id = ag.publisher_id

        try:
            await self._connection.send(msg.SerializeToString())
        except Exception as e:
            raise _transport_error(e, phase="websocket_handshake", action="send session configuration") from e

    async def _await_confirm_session(self) -> str:
        try:
            raw = await self._connection.recv()
        except Exception as e:
            raise _transport_error(e, phase="websocket_handshake", action="receive handshake response") from e

        if not isinstance(raw, (bytes, bytearray)):
            raise AvatarSDKError(
                code=AvatarSDKErrorCode.protocolError,
                message="Handshake failed: expected binary protobuf message",
                phase="websocket_handshake",
            )

        envelope = message_pb2.Message()
        try:
            envelope.ParseFromString(bytes(raw))
        except Exception as e:
            raise AvatarSDKError(
                code=AvatarSDKErrorCode.protocolError,
                message=f"Handshake failed: invalid protobuf payload ({e})",
                phase="websocket_handshake",
            ) from e

        if envelope.type == message_pb2.MESSAGE_SERVER_CONFIRM_SESSION:
            confirm = envelope.server_confirm_session
            if not confirm.connection_id:
                raise AvatarSDKError(
                    code=AvatarSDKErrorCode.protocolError,
                    message="Handshake succeeded but connection_id is empty",
                    phase="websocket_handshake",
                )
            # Forward-compatible: the field lands with server-side playback
            # control; older protos simply don't have it.
            self._capabilities = tuple(getattr(confirm, "capabilities", ()) or ())
            return confirm.connection_id

        if envelope.type == message_pb2.MESSAGE_SERVER_ERROR:
            raise _server_error(envelope.server_error, phase="websocket_handshake")

        raise AvatarSDKError(
            code=AvatarSDKErrorCode.protocolError,
            message=f"Unexpected message during handshake: type={envelope.type}",
            phase="websocket_handshake",
        )

    # ----------------------------------------------------------------- audio

    async def send_audio(self, audio: bytes, end: bool = False) -> str:
        """Send one audio chunk; returns the request id for the current segment.

        A segment spans calls until ``end=True`` (or ``interrupt()``); each new
        segment gets a fresh, never-reused request id. Raises on a dead
        connection — callers use that to trigger their recovery path.
        """
        if self._connection is None:
            raise ValueError("WebSocket connection is not established")

        if not self._current_req_id:
            self._current_req_id = generate_log_id()
            self._last_req_id = self._current_req_id
        req_id = self._current_req_id

        msg = message_pb2.Message()
        msg.type = message_pb2.MESSAGE_CLIENT_AUDIO_INPUT
        msg.client_audio_input.req_id = req_id
        msg.client_audio_input.audio = audio
        msg.client_audio_input.end = end

        try:
            await self._connection.send(msg.SerializeToString())
        except Exception as e:
            raise _transport_error(e, phase="websocket_send", action="send audio", req_id=req_id) from e

        if end:
            self._current_req_id = None
        return req_id

    async def interrupt(self) -> str:
        """Interrupt the most recent request; returns its request id."""
        if self._connection is None:
            raise ValueError("interrupt: websocket connection is not established")
        req_id = self._last_req_id
        if not req_id:
            raise ValueError("interrupt: no request to interrupt")

        msg = message_pb2.Message()
        msg.type = message_pb2.MESSAGE_CLIENT_INTERRUPT
        msg.client_interrupt.req_id = req_id

        try:
            await self._connection.send(msg.SerializeToString())
        except Exception as e:
            raise _transport_error(e, phase="websocket_send", action="send interrupt", req_id=req_id) from e

        self._current_req_id = None
        return req_id

    # ----------------------------------------------------------------- close

    async def close(self) -> None:
        """Close the connection and release resources. Idempotent.

        ``on_close`` fires exactly once per session, no matter how many times
        ``close()`` runs or whether the read loop triggered it.
        """
        conn, self._connection = self._connection, None
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass

        if self._read_task is not None and asyncio.current_task() is not self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        if not self._close_notified:
            self._close_notified = True
            if self._config.on_close:
                try:
                    self._config.on_close()
                except Exception:
                    logger.exception("on_close callback raised")

    # ------------------------------------------------------------- read loop

    async def _read_loop(self) -> None:
        connection = self._connection
        if connection is None:
            return
        try:
            async for message in connection:
                if isinstance(message, bytes):
                    self._handle_binary_message(message)
        except websockets.exceptions.ConnectionClosedOK:
            pass
        except websockets.exceptions.ConnectionClosed as e:
            close_code = getattr(getattr(e, "rcvd", None), "code", None)
            close_reason = getattr(getattr(e, "rcvd", None), "reason", None)
            self._notify_error(
                AvatarSDKError(
                    code=error_code_for_close_code(close_code),
                    message=f"WebSocket connection closed: {e}",
                    phase="websocket_runtime",
                    close_code=close_code,
                    close_reason=close_reason,
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._notify_error(
                AvatarSDKError(
                    code=AvatarSDKErrorCode.connectionFailed,
                    message=f"Read loop error: {e}",
                    phase="websocket_runtime",
                )
            )
        finally:
            await self.close()

    def _handle_binary_message(self, payload: bytes) -> None:
        envelope = message_pb2.Message()
        try:
            envelope.ParseFromString(payload)
        except Exception as e:
            self._notify_error(
                AvatarSDKError(
                    code=AvatarSDKErrorCode.protocolError,
                    message=f"Failed to decode message: {e}",
                    phase="websocket_runtime",
                )
            )
            return

        if envelope.type == message_pb2.MESSAGE_SERVER_RESPONSE_ANIMATION:
            anim = envelope.server_response_animation
            if self._config.on_playback:
                signal = PlaybackSignal(
                    req_id=anim.req_id,
                    end=bool(anim.end),
                    connection_id=anim.connection_id,
                    avatar_id=anim.avatar_id,
                    has_animation=len(anim.animation.keyframes) > 0,
                )
                try:
                    self._config.on_playback(signal)
                except Exception:
                    logger.exception("on_playback callback raised")
            if self._config.transport_frames:
                try:
                    self._config.transport_frames(bytes(payload), bool(anim.end))
                except Exception:
                    logger.exception("transport_frames callback raised")
        elif envelope.type == message_pb2.MESSAGE_SERVER_ERROR:
            self._notify_error(_server_error(envelope.server_error, phase="websocket_runtime"))
        # Unknown message types are ignored on purpose: the server may add new
        # lifecycle messages, and old clients must keep working.

    def _notify_error(self, error: Exception) -> None:
        if self._config.on_error:
            try:
                self._config.on_error(error)
            except Exception:
                logger.exception("on_error callback raised")
        else:
            logger.error("avatar session error (no on_error handler): %s", error)


# --------------------------------------------------------------------- helpers


async def _ws_connect(ws_url: str, headers: dict[str, str]):
    # websockets renamed extra_headers -> additional_headers across major
    # versions; passing the wrong kwarg leaks into asyncio.create_connection.
    params = inspect.signature(websockets.connect).parameters
    if "additional_headers" in params:
        return await websockets.connect(ws_url, additional_headers=headers)
    return await websockets.connect(ws_url, extra_headers=headers)


def _try_parse_json(body: str) -> Any:
    if not body:
        return None
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return None


def _session_token_endpoint(console_endpoint_url: str) -> str:
    """Build the session-token URL from the OpenAPI root.

    ``console_endpoint_url`` is the OpenAPI root (``https://api.spatialreal.cloud``). A value
    that still carries the old ``/v1/console`` suffix is accepted and normalized.
    """
    base = console_endpoint_url.rstrip("/")
    if base.endswith(LEGACY_CONSOLE_SUFFIX):
        base = base[: -len(LEGACY_CONSOLE_SUFFIX)]
    return base + SESSION_TOKEN_PATH


def _session_token_error(status: int, data: Any, body: str) -> SessionTokenError:
    server_code = None
    detail = None
    if isinstance(data, dict):
        errors = data.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            first = errors[0]
            server_code = str(first.get("code")) if first.get("code") is not None else None
            detail = first.get("detail") or first.get("title")
    code = {
        401: AvatarSDKErrorCode.sessionTokenInvalid,
        402: AvatarSDKErrorCode.billingRequired,
        403: AvatarSDKErrorCode.appIDUnrecognized,
        404: AvatarSDKErrorCode.avatarNotFound,
        429: AvatarSDKErrorCode.concurrencyLimit,
    }.get(status, AvatarSDKErrorCode.serverError if status >= 500 else AvatarSDKErrorCode.invalidRequest)
    message = f"Session token request failed (HTTP {status})"
    if detail:
        message = f"{message}: {detail}"
    return SessionTokenError(
        message,
        code=code,
        http_status=status,
        server_code=server_code,
        server_detail=detail,
        raw_body=body[:2048] if body else None,
    )


def _ws_connect_error(exc: Exception) -> AvatarSDKError:
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    code = AvatarSDKErrorCode.connectionFailed
    if status in (401, 403):
        code = AvatarSDKErrorCode.sessionTokenInvalid
    return AvatarSDKError(
        code=code,
        message=f"WebSocket connection failed: {exc}",
        phase="websocket_connect",
        http_status=status if isinstance(status, int) else None,
    )


def _transport_error(exc: Exception, *, phase: str, action: str, req_id: str | None = None) -> AvatarSDKError:
    close_code = getattr(getattr(exc, "rcvd", None), "code", None)
    return AvatarSDKError(
        code=(
            error_code_for_close_code(close_code)
            if isinstance(exc, websockets.exceptions.ConnectionClosed)
            else AvatarSDKErrorCode.connectionFailed
        ),
        message=f"Failed to {action}: {exc}",
        phase=phase,
        req_id=req_id,
        close_code=close_code,
    )


def _server_error(err, *, phase: str) -> AvatarSDKError:
    # ServerError.code carries a WS close code (4000-4999) for session-fate
    # errors, but relayed upstream failures use gRPC codes — only the close-code
    # range participates in the retryability contract.
    close_code = err.code if err.code and 4000 <= err.code <= 4999 else None
    return AvatarSDKError(
        code=error_code_for_close_code(close_code) if close_code else AvatarSDKErrorCode.serverError,
        message=f"Server error (code={err.code}): {err.message}" if err.message else f"Server error (code={err.code})",
        phase=phase,
        connection_id=err.connection_id or None,
        req_id=err.req_id or None,
        server_code=str(err.code),
        server_detail=err.message or None,
        close_code=close_code,
    )


def new_avatar_session(**kwargs) -> AvatarSession:
    """Create an :class:`AvatarSession` from keyword arguments.

    Accepts the same keywords as :class:`~spatialreal.SessionConfig`. Kept as a
    factory (rather than only the dataclass) so callers migrating from the
    retired avatarkit SDK change one import and nothing else.
    """
    known = set(SessionConfig.__dataclass_fields__)
    unknown = set(kwargs) - known
    if unknown:
        raise TypeError(f"Unknown session options: {sorted(unknown)}")
    return AvatarSession(SessionConfig(**kwargs))
