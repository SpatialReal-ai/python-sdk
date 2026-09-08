"""Error taxonomy for the SpatialReal SDK.

Error codes keep the names the retired avatarkit SDK used, so migrating callers
can keep their logging/branching. New in this SDK: ``CloseCode`` mirrors the
server's WebSocket close-code contract (40xx = the request is at fault, retrying
changes nothing; 45xx = the server is briefly unable, retry with backoff), and
``AvatarSDKError.retryable`` answers "should I reconnect?" so callers don't have
to memorize the ranges.
"""

from __future__ import annotations

from enum import Enum, IntEnum


class AvatarSDKErrorCode(str, Enum):
    """Stable, log-friendly error codes surfaced by the SDK."""

    sessionTokenExpired = "sessionTokenExpired"
    sessionTokenInvalid = "sessionTokenInvalid"
    appIDUnrecognized = "appIDUnrecognized"
    appIDMismatch = "appIDMismatch"
    avatarNotFound = "avatarNotFound"
    billingRequired = "billingRequired"
    creditsExhausted = "creditsExhausted"
    sessionDurationExceeded = "sessionDurationExceeded"
    concurrencyLimit = "concurrencyLimit"
    unsupportedSampleRate = "unsupportedSampleRate"
    invalidEgressConfig = "invalidEgressConfig"
    egressUnavailable = "egressUnavailable"
    idleTimeout = "idleTimeout"
    upstreamError = "upstreamError"
    invalidRequest = "invalidRequest"
    connectionFailed = "connectionFailed"
    connectionClosed = "connectionClosed"
    protocolError = "protocolError"
    serverError = "serverError"
    unknown = "unknown"


class CloseCode(IntEnum):
    """WebSocket close codes the server sends when it ends a session.

    A client contract, not diagnostics (mirrors driveningress/v2 proto):
    40xx — the request itself is at fault; do not reconnect.
    45xx — transient server-side trouble; reconnect with backoff.
    """

    CREDITS_EXHAUSTED = 4001
    SESSION_TIMEOUT = 4002
    CONCURRENCY_LIMIT = 4003
    AUTH_FAILED = 4010
    UPSTREAM_UNAVAILABLE = 4503


# Close codes for which reconnecting is expected to work.
_RETRYABLE_CLOSE_CODES = frozenset(
    {
        int(CloseCode.SESSION_TIMEOUT),  # proto: "Reconnect is allowed and expected"
        int(CloseCode.UPSTREAM_UNAVAILABLE),
    }
)

_CLOSE_CODE_TO_ERROR = {
    int(CloseCode.CREDITS_EXHAUSTED): AvatarSDKErrorCode.creditsExhausted,
    int(CloseCode.SESSION_TIMEOUT): AvatarSDKErrorCode.sessionDurationExceeded,
    int(CloseCode.CONCURRENCY_LIMIT): AvatarSDKErrorCode.concurrencyLimit,
    int(CloseCode.AUTH_FAILED): AvatarSDKErrorCode.sessionTokenInvalid,
    int(CloseCode.UPSTREAM_UNAVAILABLE): AvatarSDKErrorCode.upstreamError,
}


class AvatarSDKError(Exception):
    """SDK exception with a stable error code and structured context."""

    def __init__(
        self,
        code: AvatarSDKErrorCode,
        message: str,
        *,
        phase: str = "unknown",
        http_status: int | None = None,
        server_code: str | None = None,
        server_detail: str | None = None,
        connection_id: str | None = None,
        req_id: str | None = None,
        raw_body: str | None = None,
        close_code: int | None = None,
        close_reason: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.phase = phase
        self.http_status = http_status
        self.server_code = server_code
        self.server_detail = server_detail
        self.connection_id = connection_id
        self.req_id = req_id
        self.raw_body = raw_body
        self.close_code = close_code
        self.close_reason = close_reason

    @property
    def retryable(self) -> bool:
        """Whether reconnecting can plausibly succeed, per the close-code contract.

        Unknown/absent close codes count as retryable: transport-level failures
        (network blips, process restarts) close without our 40xx codes, and for
        those, giving up for good is the wrong default.
        """
        if self.close_code is None:
            return self.code in (
                AvatarSDKErrorCode.connectionFailed,
                AvatarSDKErrorCode.connectionClosed,
                AvatarSDKErrorCode.upstreamError,
            )
        if self.close_code in _RETRYABLE_CLOSE_CODES:
            return True
        if 4000 <= self.close_code < 4500:
            return False
        return True

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code.value}: {self.message}"


class SessionTokenError(AvatarSDKError):
    """Raised when the session-token exchange with the console API fails."""

    def __init__(
        self,
        message: str,
        *,
        code: AvatarSDKErrorCode = AvatarSDKErrorCode.invalidRequest,
        http_status: int | None = None,
        server_code: str | None = None,
        server_detail: str | None = None,
        raw_body: str | None = None,
    ):
        super().__init__(
            code=code,
            message=message,
            phase="session_token",
            http_status=http_status,
            server_code=server_code,
            server_detail=server_detail,
            raw_body=raw_body,
        )


def error_code_for_close_code(close_code: int | None) -> AvatarSDKErrorCode:
    if close_code is None:
        return AvatarSDKErrorCode.connectionClosed
    return _CLOSE_CODE_TO_ERROR.get(close_code, AvatarSDKErrorCode.connectionClosed)
