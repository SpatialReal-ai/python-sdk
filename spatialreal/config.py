"""Session configuration types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .events import PlaybackSignal, PlaybackStateEvent


class AudioFormat(str, Enum):
    """Audio input encoding negotiated for a session.

    ``PCM_S16LE``: raw PCM16 mono at ``sample_rate``.
    ``OGG_OPUS``: one continuous, pre-encoded Ogg Opus stream per request id
    (this SDK does not encode client-side; send encoded bytes).
    """

    PCM_S16LE = "pcm_s16le"
    OGG_OPUS = "ogg_opus"


@dataclass
class LiveKitEgressConfig:
    """Stream the avatar's audio/video into a LiveKit room via the egress service.

    When set on a session, animation is NOT returned over the WebSocket; the
    egress worker joins the room and publishes synchronized tracks. The WebSocket
    carries only control/lifecycle messages.
    """

    url: str = ""
    api_token: str = field(default="", repr=False)
    room_name: str = ""
    publisher_id: str = ""
    extra_attributes: dict[str, str] = field(default_factory=dict)
    # 0 = server default. Server closes the egress connection when completely silent.
    idle_timeout: int = 0
    # Deprecated pair, kept for wire compatibility; prefer api_token.
    api_key: str = field(default="", repr=False)
    api_secret: str = field(default="", repr=False)


@dataclass
class AgoraEgressConfig:
    """Stream the avatar's audio/video into an Agora channel via the egress service."""

    channel_name: str = ""
    token: str = field(default="", repr=False)
    uid: int = 0
    publisher_id: str = ""


@dataclass
class SessionConfig:
    """Configuration for an :class:`~spatialreal.AvatarSession`.

    Callback contract (all callbacks run on the session's event loop and must
    not block):

    - ``on_playback(signal)``: structured playback lifecycle parsed from
      ``ServerResponseAnimation`` — preferred over ``transport_frames``.
    - ``on_playback_state(event)``: structured ``ServerPlaybackState`` for
      egress-mode playback control (pause/resume/interrupt position); only
      arrives when the server declares the ``playback_state`` capability.
    - ``transport_frames(frame_bytes, is_last)``: the raw serialized ``Message``
      envelope, for callers that decode the protobuf themselves.
    - ``on_error(error)``: transport/server errors outside a call site (read
      loop). Errors raised by ``send_audio``/``interrupt`` are raised, not
      routed here.
    - ``on_close()``: fired exactly once when the session ends, whether by
      ``close()`` or by the connection dropping.
    """

    avatar_id: str = ""
    api_key: str = field(default="", repr=False)
    app_id: str = ""
    # v2 auth style: False = headers (mobile-style), True = URL query params (web-style).
    use_query_auth: bool = False
    expire_at: datetime | None = None
    sample_rate: int = 16000
    bitrate: int = 0
    audio_format: AudioFormat = AudioFormat.PCM_S16LE
    console_endpoint_url: str = ""
    ingress_endpoint_url: str = ""
    livekit_egress: LiveKitEgressConfig | None = None
    agora_egress: AgoraEgressConfig | None = None

    on_playback: Callable[[PlaybackSignal], None] | None = None
    on_playback_state: Callable[[PlaybackStateEvent], None] | None = None
    transport_frames: Callable[[bytes, bool], None] | None = None
    on_error: Callable[[Exception], None] | None = None
    on_close: Callable[[], None] | None = None

    # Timeout for the console session-token HTTP call.
    token_request_timeout: float = 30.0

    def __post_init__(self) -> None:
        self.audio_format = AudioFormat(self.audio_format)
