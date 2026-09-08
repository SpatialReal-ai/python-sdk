from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MessageType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MESSAGE_UNSPECIFIED: _ClassVar[MessageType]
    MESSAGE_CLIENT_CONFIGURE_SESSION: _ClassVar[MessageType]
    MESSAGE_SERVER_CONFIRM_SESSION: _ClassVar[MessageType]
    MESSAGE_CLIENT_AUDIO_INPUT: _ClassVar[MessageType]
    MESSAGE_SERVER_ERROR: _ClassVar[MessageType]
    MESSAGE_SERVER_RESPONSE_ANIMATION: _ClassVar[MessageType]
    MESSAGE_CLIENT_DRIVEN_CONFIG: _ClassVar[MessageType]
    MESSAGE_CLIENT_INTERRUPT: _ClassVar[MessageType]

class AudioFormat(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AUDIO_FORMAT_PCM_S16LE: _ClassVar[AudioFormat]
    AUDIO_FORMAT_OGG_OPUS: _ClassVar[AudioFormat]

class TransportCompression(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TRANSPORT_COMPRESSION_NONE: _ClassVar[TransportCompression]

class EgressType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EGRESS_TYPE_UNSPECIFIED: _ClassVar[EgressType]
    EGRESS_TYPE_LIVEKIT: _ClassVar[EgressType]
    EGRESS_TYPE_AGORA: _ClassVar[EgressType]

class CloseCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CLOSE_CODE_UNSPECIFIED: _ClassVar[CloseCode]
    CLOSE_CODE_CREDITS_EXHAUSTED: _ClassVar[CloseCode]
    CLOSE_CODE_SESSION_TIMEOUT: _ClassVar[CloseCode]
    CLOSE_CODE_CONCURRENCY_LIMIT: _ClassVar[CloseCode]
    CLOSE_CODE_AUTH_FAILED: _ClassVar[CloseCode]
    CLOSE_CODE_UPSTREAM_UNAVAILABLE: _ClassVar[CloseCode]
MESSAGE_UNSPECIFIED: MessageType
MESSAGE_CLIENT_CONFIGURE_SESSION: MessageType
MESSAGE_SERVER_CONFIRM_SESSION: MessageType
MESSAGE_CLIENT_AUDIO_INPUT: MessageType
MESSAGE_SERVER_ERROR: MessageType
MESSAGE_SERVER_RESPONSE_ANIMATION: MessageType
MESSAGE_CLIENT_DRIVEN_CONFIG: MessageType
MESSAGE_CLIENT_INTERRUPT: MessageType
AUDIO_FORMAT_PCM_S16LE: AudioFormat
AUDIO_FORMAT_OGG_OPUS: AudioFormat
TRANSPORT_COMPRESSION_NONE: TransportCompression
EGRESS_TYPE_UNSPECIFIED: EgressType
EGRESS_TYPE_LIVEKIT: EgressType
EGRESS_TYPE_AGORA: EgressType
CLOSE_CODE_UNSPECIFIED: CloseCode
CLOSE_CODE_CREDITS_EXHAUSTED: CloseCode
CLOSE_CODE_SESSION_TIMEOUT: CloseCode
CLOSE_CODE_CONCURRENCY_LIMIT: CloseCode
CLOSE_CODE_AUTH_FAILED: CloseCode
CLOSE_CODE_UPSTREAM_UNAVAILABLE: CloseCode

class LiveKitEgressConfig(_message.Message):
    __slots__ = ("url", "api_key", "api_secret", "room_name", "publisher_id", "extra_attributes", "idle_timeout", "api_token")
    class ExtraAttributesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    URL_FIELD_NUMBER: _ClassVar[int]
    API_KEY_FIELD_NUMBER: _ClassVar[int]
    API_SECRET_FIELD_NUMBER: _ClassVar[int]
    ROOM_NAME_FIELD_NUMBER: _ClassVar[int]
    PUBLISHER_ID_FIELD_NUMBER: _ClassVar[int]
    EXTRA_ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    IDLE_TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    API_TOKEN_FIELD_NUMBER: _ClassVar[int]
    url: str
    api_key: str
    api_secret: str
    room_name: str
    publisher_id: str
    extra_attributes: _containers.ScalarMap[str, str]
    idle_timeout: int
    api_token: str
    def __init__(self, url: _Optional[str] = ..., api_key: _Optional[str] = ..., api_secret: _Optional[str] = ..., room_name: _Optional[str] = ..., publisher_id: _Optional[str] = ..., extra_attributes: _Optional[_Mapping[str, str]] = ..., idle_timeout: _Optional[int] = ..., api_token: _Optional[str] = ...) -> None: ...

class AgoraEgressConfig(_message.Message):
    __slots__ = ("channel_name", "token", "uid", "publisher_id")
    CHANNEL_NAME_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    UID_FIELD_NUMBER: _ClassVar[int]
    PUBLISHER_ID_FIELD_NUMBER: _ClassVar[int]
    channel_name: str
    token: str
    uid: int
    publisher_id: str
    def __init__(self, channel_name: _Optional[str] = ..., token: _Optional[str] = ..., uid: _Optional[int] = ..., publisher_id: _Optional[str] = ...) -> None: ...

class DrivenIngressConfig(_message.Message):
    __slots__ = ("shape_npy", "style_npy", "driven_server_url", "model_settings", "encoder_start_frame")
    SHAPE_NPY_FIELD_NUMBER: _ClassVar[int]
    STYLE_NPY_FIELD_NUMBER: _ClassVar[int]
    DRIVEN_SERVER_URL_FIELD_NUMBER: _ClassVar[int]
    MODEL_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    ENCODER_START_FRAME_FIELD_NUMBER: _ClassVar[int]
    shape_npy: bytes
    style_npy: bytes
    driven_server_url: str
    model_settings: _struct_pb2.Struct
    encoder_start_frame: int
    def __init__(self, shape_npy: _Optional[bytes] = ..., style_npy: _Optional[bytes] = ..., driven_server_url: _Optional[str] = ..., model_settings: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., encoder_start_frame: _Optional[int] = ...) -> None: ...

class ClientConfigureSession(_message.Message):
    __slots__ = ("sample_rate", "bitrate", "audio_format", "transport_compression", "egress_type", "livekit_egress", "agora_egress")
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    BITRATE_FIELD_NUMBER: _ClassVar[int]
    AUDIO_FORMAT_FIELD_NUMBER: _ClassVar[int]
    TRANSPORT_COMPRESSION_FIELD_NUMBER: _ClassVar[int]
    EGRESS_TYPE_FIELD_NUMBER: _ClassVar[int]
    LIVEKIT_EGRESS_FIELD_NUMBER: _ClassVar[int]
    AGORA_EGRESS_FIELD_NUMBER: _ClassVar[int]
    sample_rate: int
    bitrate: int
    audio_format: AudioFormat
    transport_compression: TransportCompression
    egress_type: EgressType
    livekit_egress: LiveKitEgressConfig
    agora_egress: AgoraEgressConfig
    def __init__(self, sample_rate: _Optional[int] = ..., bitrate: _Optional[int] = ..., audio_format: _Optional[_Union[AudioFormat, str]] = ..., transport_compression: _Optional[_Union[TransportCompression, str]] = ..., egress_type: _Optional[_Union[EgressType, str]] = ..., livekit_egress: _Optional[_Union[LiveKitEgressConfig, _Mapping]] = ..., agora_egress: _Optional[_Union[AgoraEgressConfig, _Mapping]] = ...) -> None: ...

class ServerConfirmSession(_message.Message):
    __slots__ = ("connection_id",)
    CONNECTION_ID_FIELD_NUMBER: _ClassVar[int]
    connection_id: str
    def __init__(self, connection_id: _Optional[str] = ...) -> None: ...

class ClientAudioInput(_message.Message):
    __slots__ = ("req_id", "end", "audio")
    REQ_ID_FIELD_NUMBER: _ClassVar[int]
    END_FIELD_NUMBER: _ClassVar[int]
    AUDIO_FIELD_NUMBER: _ClassVar[int]
    req_id: str
    end: bool
    audio: bytes
    def __init__(self, req_id: _Optional[str] = ..., end: bool = ..., audio: _Optional[bytes] = ...) -> None: ...

class ServerError(_message.Message):
    __slots__ = ("connection_id", "req_id", "code", "message")
    CONNECTION_ID_FIELD_NUMBER: _ClassVar[int]
    REQ_ID_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    connection_id: str
    req_id: str
    code: int
    message: str
    def __init__(self, connection_id: _Optional[str] = ..., req_id: _Optional[str] = ..., code: _Optional[int] = ..., message: _Optional[str] = ...) -> None: ...

class Flame(_message.Message):
    __slots__ = ("translation", "rotation", "neck_pose", "jaw_pose", "eye_pose", "eye_lid", "expression")
    TRANSLATION_FIELD_NUMBER: _ClassVar[int]
    ROTATION_FIELD_NUMBER: _ClassVar[int]
    NECK_POSE_FIELD_NUMBER: _ClassVar[int]
    JAW_POSE_FIELD_NUMBER: _ClassVar[int]
    EYE_POSE_FIELD_NUMBER: _ClassVar[int]
    EYE_LID_FIELD_NUMBER: _ClassVar[int]
    EXPRESSION_FIELD_NUMBER: _ClassVar[int]
    translation: _containers.RepeatedScalarFieldContainer[float]
    rotation: _containers.RepeatedScalarFieldContainer[float]
    neck_pose: _containers.RepeatedScalarFieldContainer[float]
    jaw_pose: _containers.RepeatedScalarFieldContainer[float]
    eye_pose: _containers.RepeatedScalarFieldContainer[float]
    eye_lid: _containers.RepeatedScalarFieldContainer[float]
    expression: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, translation: _Optional[_Iterable[float]] = ..., rotation: _Optional[_Iterable[float]] = ..., neck_pose: _Optional[_Iterable[float]] = ..., jaw_pose: _Optional[_Iterable[float]] = ..., eye_pose: _Optional[_Iterable[float]] = ..., eye_lid: _Optional[_Iterable[float]] = ..., expression: _Optional[_Iterable[float]] = ...) -> None: ...

class FlameAnimation(_message.Message):
    __slots__ = ("keyframes",)
    KEYFRAMES_FIELD_NUMBER: _ClassVar[int]
    keyframes: _containers.RepeatedCompositeFieldContainer[Flame]
    def __init__(self, keyframes: _Optional[_Iterable[_Union[Flame, _Mapping]]] = ...) -> None: ...

class ServerResponseAnimation(_message.Message):
    __slots__ = ("connection_id", "req_id", "end", "animation", "avatar_id")
    CONNECTION_ID_FIELD_NUMBER: _ClassVar[int]
    REQ_ID_FIELD_NUMBER: _ClassVar[int]
    END_FIELD_NUMBER: _ClassVar[int]
    ANIMATION_FIELD_NUMBER: _ClassVar[int]
    AVATAR_ID_FIELD_NUMBER: _ClassVar[int]
    connection_id: str
    req_id: str
    end: bool
    animation: FlameAnimation
    avatar_id: str
    def __init__(self, connection_id: _Optional[str] = ..., req_id: _Optional[str] = ..., end: bool = ..., animation: _Optional[_Union[FlameAnimation, _Mapping]] = ..., avatar_id: _Optional[str] = ...) -> None: ...

class ClientInterrupt(_message.Message):
    __slots__ = ("req_id",)
    REQ_ID_FIELD_NUMBER: _ClassVar[int]
    req_id: str
    def __init__(self, req_id: _Optional[str] = ...) -> None: ...

class Message(_message.Message):
    __slots__ = ("type", "client_configure_session", "server_confirm_session", "client_audio_input", "server_error", "server_response_animation", "driven_config", "client_interrupt")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    CLIENT_CONFIGURE_SESSION_FIELD_NUMBER: _ClassVar[int]
    SERVER_CONFIRM_SESSION_FIELD_NUMBER: _ClassVar[int]
    CLIENT_AUDIO_INPUT_FIELD_NUMBER: _ClassVar[int]
    SERVER_ERROR_FIELD_NUMBER: _ClassVar[int]
    SERVER_RESPONSE_ANIMATION_FIELD_NUMBER: _ClassVar[int]
    DRIVEN_CONFIG_FIELD_NUMBER: _ClassVar[int]
    CLIENT_INTERRUPT_FIELD_NUMBER: _ClassVar[int]
    type: MessageType
    client_configure_session: ClientConfigureSession
    server_confirm_session: ServerConfirmSession
    client_audio_input: ClientAudioInput
    server_error: ServerError
    server_response_animation: ServerResponseAnimation
    driven_config: DrivenIngressConfig
    client_interrupt: ClientInterrupt
    def __init__(self, type: _Optional[_Union[MessageType, str]] = ..., client_configure_session: _Optional[_Union[ClientConfigureSession, _Mapping]] = ..., server_confirm_session: _Optional[_Union[ServerConfirmSession, _Mapping]] = ..., client_audio_input: _Optional[_Union[ClientAudioInput, _Mapping]] = ..., server_error: _Optional[_Union[ServerError, _Mapping]] = ..., server_response_animation: _Optional[_Union[ServerResponseAnimation, _Mapping]] = ..., driven_config: _Optional[_Union[DrivenIngressConfig, _Mapping]] = ..., client_interrupt: _Optional[_Union[ClientInterrupt, _Mapping]] = ...) -> None: ...
