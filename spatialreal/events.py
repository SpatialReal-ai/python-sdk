"""Structured events the SDK surfaces to callers."""

from __future__ import annotations

from dataclasses import dataclass


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
