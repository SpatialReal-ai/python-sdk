# SpatialReal Python SDK

`pip install spatialreal` — realtime avatar sessions against the SpatialReal
backend: stream audio in, get lifecycle signals back, and (in egress mode) have
the avatar's synchronized audio/video published straight into a LiveKit room or
Agora channel.

Successor to the retired `avatarkit` package: same wire protocol, same session
semantics. Migrating is one import swap (`from avatarkit import ...` →
`from spatialreal import ...`).

## Usage

```python
from datetime import datetime, timedelta, timezone
from spatialreal import LiveKitEgressConfig, new_avatar_session

session = new_avatar_session(
    api_key="...",
    app_id="...",
    avatar_id="...",
    console_endpoint_url="https://api.spatialreal.com",  # OpenAPI root: session tokens
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

Session objects are single-use: on a dropped connection, create a fresh one
(request state is deliberately not reusable across connections).
`AvatarSDKError.retryable` tells you whether reconnecting can succeed — it
implements the server's WebSocket close-code contract (40xx: don't retry,
45xx: retry with backoff).

## What's new vs avatarkit

- `on_playback(PlaybackSignal)` — structured playback lifecycle; no protobuf
  parsing in caller code (`transport_frames(raw, is_last)` still exists).
- `CloseCode` + `AvatarSDKError.retryable` — the reconnect contract as API.
- `session.capabilities` — server-declared capabilities from the handshake
  (feature-detect, don't version-detect).
- `on_close` fires exactly once per session; the token request has a timeout.
- Not carried over (yet): client-side Ogg Opus encoding. `AudioFormat.OGG_OPUS`
  works with pre-encoded bytes.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
python -m pytest tests -q     # protocol-level tests against an in-process fake backend
./scripts/gen_proto.sh        # regenerate protobuf from proto/ (see proto/SHARED_PROTO_COMMIT)
```

## License

Apache-2.0
