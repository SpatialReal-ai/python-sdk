# Copyright 2026 SpatialReal.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""SpatialReal Python SDK — realtime avatar sessions.

Successor to the retired ``avatarkit`` package: same wire protocol and session
semantics, one import swap for existing callers, plus structured playback
events (``on_playback``) and the WebSocket close-code contract (``CloseCode``,
``AvatarSDKError.retryable``).
"""

from .config import (
    AgoraEgressConfig,
    AudioFormat,
    LiveKitEgressConfig,
    SessionConfig,
)
from .errors import AvatarSDKError, AvatarSDKErrorCode, CloseCode, SessionTokenError
from .events import InterruptReason, PlaybackSignal, PlaybackState, PlaybackStateEvent
from .logid import generate_log_id
from .session import AvatarSession, new_avatar_session
from .version import __version__

__all__ = [
    "AgoraEgressConfig",
    "AudioFormat",
    "AvatarSDKError",
    "AvatarSDKErrorCode",
    "AvatarSession",
    "CloseCode",
    "LiveKitEgressConfig",
    "PlaybackSignal",
    "PlaybackStateEvent",
    "PlaybackState",
    "InterruptReason",
    "SessionConfig",
    "SessionTokenError",
    "__version__",
    "generate_log_id",
    "new_avatar_session",
]
