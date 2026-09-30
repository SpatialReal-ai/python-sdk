# SpatialReal Python SDK

`pip install spatialreal` — realtime avatar sessions against the SpatialReal
backend: stream audio in, get lifecycle signals back, and (in egress mode) have
the avatar's synchronized audio/video published straight into a LiveKit room or
Agora channel.

## Usage

```python
from datetime import datetime, timedelta, timezone
from spatialreal import LiveKitEgressConfig, new_avatar_session

session = new_avatar_session(
    api_key="...",
    app_id="...",
    avatar_id="...",
    console_endpoint_url="https://api.spatialreal.cloud",  # OpenAPI root: session tokens
    ingress_endpoint_url="wss://driven.us-west.spatialreal.cloud/v2/driveningress",
    expire_at=datetime.now(timezone.utc) + timedelta(hours=1),
    sample_rate=16000,
    livekit_egress=LiveKitEgressConfig(url=..., api_token=..., room_name=..., publisher_id=...),
    on_playback=lambda sig: print(sig.req_id, "ended" if sig.end else "playing"),
    on_error=lambda err: print("error:", err, "retryable:", getattr(err, "retryable", None)),
    on_close=lambda: print("closed"),
)
await session.init()  # API key -> session token (console API)
await session.start()  # WebSocket + handshake; read loop starts

req_id = await session.send_audio(pcm_bytes)  # same id until end=True
await session.send_audio(b"", end=True)  # closes the segment
await session.interrupt()  # interrupts the latest request
await session.close()
```

### Pause / resume (egress mode)

When the server declares the `playback_control` capability, the current
segment can be paused and resumed instead of interrupted — the server holds
its send cursor with zero regeneration:

```python
await session.pause()  # server stops writing frames, keeps ingesting audio
# ...keep sending audio, including end=True, while paused...
await session.resume()  # continues from where it stopped
```

Feature-detect with `"playback_control" in session.capabilities`. Subscribe to
`on_playback_state(PlaybackStateEvent)` for the resulting state (PLAYING /
PAUSED / ENDED / INTERRUPTED with `played_ms` and, on interrupt, a `reason` such
as `pause_timeout`). Older servers never send it and ignore pause/resume.

Session objects are single-use: on a dropped connection, create a fresh one
(request state is deliberately not reusable across connections).
`AvatarSDKError.retryable` tells you whether reconnecting can succeed — it
implements the server's WebSocket close-code contract (40xx: don't retry,
45xx: retry with backoff).

## What's new

- `on_playback(PlaybackSignal)` — structured playback lifecycle; no protobuf
  parsing in caller code (`transport_frames(raw, is_last)` still exists).
- `CloseCode` + `AvatarSDKError.retryable` — the reconnect contract as API.
- `session.capabilities` — server-declared capabilities from the handshake
  (feature-detect, don't version-detect).
- `pause()` / `resume()` + `on_playback_state(PlaybackStateEvent)` — egress-mode
  server-side playback control (gated on the `playback_control` capability).
- `on_close` fires exactly once per session; the token request has a timeout.
- `AudioFormat.OGG_OPUS` takes pre-encoded bytes; the SDK does not encode
  client-side.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
python -m pytest tests -q     # protocol-level tests against an in-process fake backend
./scripts/gen_proto.sh        # regenerate protobuf from proto/ (see proto/SHARED_PROTO_COMMIT)
```

## License

Apache-2.0
