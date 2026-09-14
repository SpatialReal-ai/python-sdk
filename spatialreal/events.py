"""Structured events the SDK surfaces to callers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class PlaybackSignal:
    """Playback lifecycle parsed from a ``ServerResponseAnimation`` message.

    Semantics depend on the delivery mode:

    - WebSocket direct return: frames carry animation data; ``end=True`` means
      generation for the request is complete.
    - LiveKit/Agora egress: frames are empty control signals; a non-end frame
      marks playback progress/start and ``end=True`` means the egress playout
      for the request has fully drained. Egress-path retransmission can deliver
      ``end=True`` more than once per ``req_id`` — dedupe on the consumer side.
    """

    req_id: str
    end: bool
    connection_id: str = ""
    avatar_id: str = ""
    has_animation: bool = False


class PlaybackState(str, Enum):
    """State reported by a ``ServerPlaybackState`` message (egress mode)."""

    UNSPECIFIED = "unspecified"
    PLAYING = "playing"
    PAUSED = "paused"
    ENDED = "ended"
    INTERRUPTED = "interrupted"


class InterruptReason(str, Enum):
    """``reason`` on an INTERRUPTED playback state."""

    EXPLICIT = "explicit"  # an explicit interrupt() / client interrupt
    PREEMPTED = "preempted"  # a newer request superseded this one
    PAUSE_TIMEOUT = "pause_timeout"  # a held pause exceeded the server limit


@dataclass(frozen=True)
class PlaybackStateEvent:
    """Structured ``ServerPlaybackState`` (egress-mode playback control, #51).

    Emitted for every ``pause()``/``resume()`` (the state *after* the operation)
    and spontaneously by the server on playback start/end/interrupt. Only sent
    when the server declared the ``playback_state`` capability; older servers
    never send it. ``played_ms`` is content playout position (excludes
    transitions, does not advance while paused). ``reason`` is meaningful only
    for ``INTERRUPTED`` — notably ``pause_timeout`` means a held pause hit the
    server limit and the caller should treat the segment as interrupted (drop
    retained audio, do not resume).
    """

    req_id: str
    state: PlaybackState
    played_ms: int = 0
    reason: str = ""
    connection_id: str = ""
