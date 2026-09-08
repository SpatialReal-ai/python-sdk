"""Request/log id generation.

Format is shared with the Go backend and the retired avatarkit SDK:
"YYYYMMDDHHMMSS_<nanoid12>" (UTC). Every request gets a fresh id; ids are
never reused within a connection — the plugin's interrupt bookkeeping and the
backend's session mapping both rely on uniqueness.
"""

from datetime import datetime, timezone

from nanoid import generate

LOG_ID_TIME_FORMAT = "%Y%m%d%H%M%S"
LOG_ID_NANOID_LENGTH = 12


def generate_log_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime(LOG_ID_TIME_FORMAT)
    return f"{timestamp}_{generate(size=LOG_ID_NANOID_LENGTH)}"
