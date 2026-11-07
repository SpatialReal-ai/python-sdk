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
    avatar_id="...",
    # app_id is optional: the app is derived from the API key server-side
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

### Agora source-timeline-only viewers

Set `AgoraEgressConfig(source_timeline_only=True, ...)` only when every viewer
plays the source-timeline audio and manages its own entry transition. The default
is `False`, which retains the existing RTC delivery policy. This setting does not
change input sample rates or audio data.

`start()` requires the server's `agora_source_timeline_only` capability when this
mode is requested. A confirmation without it raises `UnsupportedConfigurationError`
(`protocolError`, `websocket_handshake`, not retryable) and closes the connection
before audio is sent. A standard WebSocket policy rejection (`1008`) is also not
retryable. Other transport failures retain their normal retry behavior.

For the coordinated bounded-burst profile, also set
`source_playback_profile=RtcSourcePlaybackProfile.BOUNDED_BURST_V1` (import the
enum from `spatialreal`). It requires `source_timeline_only=True` and both
`agora_source_timeline_only` and `agora_source_burst_v1` in the server's actual
confirmation. `session.capabilities` is the read-only tuple from that handshake.
Missing acceptance closes the connection before the read loop or audio starts;
there is no silent fallback. The default `UNSPECIFIED`/0 is omitted on the wire
and retains existing behavior. Unknown values and booleans are rejected.

Every animation viewer must independently opt into the same profile using a
compatible viewer SDK; the publisher's handshake cannot negotiate room viewers.
The profile contract is not released yet. Generated types are a local bridge
from the authored shared-proto change; merge and tag propagation remain pending.
See [the code-generation receipt](docs/source-burst-codegen.json). No PyPI release
or deployment is implied by this change.

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
## Endpoints

Endpoints come from the environment you name, so callers write no URLs:

```python
session = new_avatar_session(..., environment="us-west")  # the default
```

They are resolved from SpatialReal's config service (built-in presets cover it being
unreachable), which is what lets a deployment move, or a region be added, without an
SDK release. Pass `console_endpoint_url` / `ingress_endpoint_url` to override either one
— useful against a local or private deployment.

`AvatarSDKError.retryable` tells you whether reconnecting can succeed — it
implements the server's WebSocket close-code contract (40xx: don't retry,
45xx: retry with backoff).

## What's new

- 0.2.3: `app_id` is optional (the API key identifies the app); protobuf floor lowered
  to 5.29 so the SDK installs next to packages that pin protobuf 5.x (TEN Framework agents).
- `on_playback(PlaybackSignal)` — structured playback lifecycle; no protobuf
  parsing in caller code (`transport_frames(raw, is_last)` still exists).
- `CloseCode` + `AvatarSDKError.retryable` — the reconnect contract as API.
- `environment="us-west"` — endpoints resolved from the config service instead of
  hard-coded URLs; new regions need no SDK release.
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
```

## License

Apache-2.0
