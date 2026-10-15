import json
import traceback

from ten_runtime import (  # pylint: disable=import-error
    AsyncExtension,
    AsyncTenEnv,
    AudioFrame,
    Cmd,
    CmdResult,
    Data,
    StatusCode,
)

from .avatar import AvatarBridge, BridgeConfig


async def _prop_str(ten_env: AsyncTenEnv, name: str, default: str = "") -> str:
    try:
        value, err = await ten_env.get_property_string(name)
    except Exception:  # noqa: BLE001
        return default
    return default if err is not None or value is None else value


async def _prop_int(ten_env: AsyncTenEnv, name: str, default: int = 0) -> int:
    try:
        value, err = await ten_env.get_property_int(name)
    except Exception:  # noqa: BLE001
        return default
    return default if err is not None or value is None else int(value)


async def load_config(ten_env: AsyncTenEnv) -> BridgeConfig:
    return BridgeConfig(
        app_id=await _prop_str(ten_env, "spatialreal_app_id"),
        api_key=await _prop_str(ten_env, "spatialreal_api_key"),
        avatar_id=await _prop_str(ten_env, "spatialreal_avatar_id"),
        environment=await _prop_str(ten_env, "spatialreal_environment", "us-west") or "us-west",
        console_endpoint=await _prop_str(ten_env, "spatialreal_console_endpoint"),
        ingress_endpoint=await _prop_str(ten_env, "spatialreal_ingress_endpoint"),
        agora_app_id=await _prop_str(ten_env, "agora_appid"),
        agora_app_cert=await _prop_str(ten_env, "agora_appcert"),
        channel_name=await _prop_str(ten_env, "agora_channel_name"),
        avatar_uid=await _prop_int(ten_env, "agora_avatar_uid"),
        sample_rate=await _prop_int(ten_env, "input_audio_sample_rate", 16000),
        segment_idle_end_ms=await _prop_int(ten_env, "segment_idle_end_ms", 1500),
    )


class SpatialRealAvatarExtension(AsyncExtension):
    """TTS audio in (``pcm_frame``) → SpatialReal avatar out, published into the Agora channel.

    Sits after the TTS node in the graph, in place of (or next to) the ``agora_rtc`` audio
    sink: the avatar's own audio track carries the speech, lip-synced.
    """

    def __init__(self, name: str):
        super().__init__(name)
        self.ten_env: AsyncTenEnv | None = None
        self.bridge: AvatarBridge | None = None

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        self.ten_env = ten_env

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        try:
            cfg = await load_config(ten_env)
            ten_env.log_info(
                f"[SPATIALREAL] avatar={cfg.avatar_id} env={cfg.environment} "
                f"channel={cfg.channel_name} uid={cfg.avatar_uid} rate={cfg.sample_rate}"
            )
            self.bridge = AvatarBridge(cfg, log=lambda level, msg: self._log(level, msg))
            await self.bridge.connect()
        except Exception:  # noqa: BLE001
            ten_env.log_error(f"[SPATIALREAL] on_start failed: {traceback.format_exc()}")

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        if self.bridge is not None:
            await self.bridge.close()
            self.bridge = None
            ten_env.log_info("[SPATIALREAL] session closed")

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_deinit")

    async def on_audio_frame(self, _ten_env: AsyncTenEnv, audio_frame: AudioFrame) -> None:
        if self.bridge is None:
            return
        await self.bridge.push_audio(bytes(audio_frame.get_buf()))

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        if data.get_name() != "tts_audio_end" or self.bridge is None:
            return
        reason = None
        try:
            json_str, _ = data.get_property_to_json(None)
            if json_str:
                reason = json.loads(json_str).get("reason")
        except Exception:  # noqa: BLE001
            reason = None
        # reason 1 = TTS generation complete; other reasons (interrupted) are handled by flush
        if reason in (None, 1):
            await self.bridge.end_segment()

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        if cmd.get_name() == "flush":
            if self.bridge is not None:
                await self.bridge.interrupt()
            await ten_env.send_cmd(Cmd.create("flush"))
        await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))

    def _log(self, level: str, msg: str) -> None:
        env = self.ten_env
        if env is None:
            return
        {"debug": env.log_debug, "info": env.log_info, "warning": env.log_warn, "error": env.log_error}.get(
            level, env.log_info
        )(f"[SPATIALREAL] {msg}")
