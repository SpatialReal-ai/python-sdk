# spatialreal_avatar_python

[TEN Framework](https://github.com/TEN-framework/ten-framework) 的数字人扩展:把 TTS 出来的音频喂给
SpatialReal,SpatialReal 的 egress 以 `agora_avatar_uid` 进同一个 Agora 频道,发布形象的音频轨和动画轨。
和 `heygen_avatar_python` 放在图里的位置一样:接在 TTS 后面,替掉(或并列于)`agora_rtc` 的音频入口。

## 图里怎么接

```json
{
  "type": "extension",
  "name": "spatialreal_avatar",
  "addon": "spatialreal_avatar_python",
  "extension_group": "avatar",
  "property": {
    "spatialreal_app_id": "${env:SPATIALREAL_APP_ID|}",
    "spatialreal_api_key": "${env:SPATIALREAL_API_KEY|}",
    "spatialreal_avatar_id": "${env:SPATIALREAL_AVATAR_ID|}",
    "agora_appid": "${env:AGORA_APP_ID|}",
    "agora_appcert": "${env:AGORA_APP_CERTIFICATE|}",
    "agora_channel_name": "ten_agent_test",
    "agora_avatar_uid": 12345,
    "input_audio_sample_rate": 16000
  }
}
```

连线:TTS 的 `pcm_frame` → 本扩展 `audio_frame_in`;TTS 的 `tts_audio_end`(data)→ 本扩展;
`flush` cmd 进来会打断形象并原样转发出去。

| 属性 | 说明 |
|---|---|
| `spatialreal_app_id` / `spatialreal_api_key` / `spatialreal_avatar_id` | SpatialReal Studio 里的应用、API key、形象 |
| `spatialreal_environment` | 默认 `us-west`;`spatialreal_console_endpoint` / `spatialreal_ingress_endpoint` 可显式覆盖 |
| `agora_appid` / `agora_appcert` | 给 egress 签 RTC token(发布者角色,24 h);没有证书时直接用 App ID 当 token(Agora 测试模式) |
| `agora_channel_name` / `agora_avatar_uid` | egress 进哪个频道、用哪个 uid;uid 必须非 0 |
| `input_audio_sample_rate` | TTS 输出采样率(PCM16 单声道),原样告诉 SpatialReal,不重采样 |
| `segment_idle_end_ms` | 没收到 `tts_audio_end` 时,最后一块音频之后多久把这一句收尾(默认 1500;0 关闭) |

## 行为

- 音频按块直发;`tts_audio_end`(reason 1)或空闲超时收尾一句;`flush` → 丢掉未发的、`interrupt()`。
- 连接掉了(发送失败、`on_close`、可重试的 `on_error`)按 1/2/4/8/15/30 s 退避重建会话,进行中的那句丢弃。
- 事件只记日志(`[SPATIALREAL] ...`)。

## 两个前提(接之前先确认)

1. **egress 的 Agora App ID**:egress 的 Agora provider 用的是它部署时配的 App ID,不是每个会话传进来的
   (`AgoraEgressConfig` 只有 channel / token / uid)。所以 `agora_appid` 必须和 SpatialReal 这套 egress 配的一致,
   否则 token 校验不过、进不了频道。要给任意客户的 Agora 项目用,需要 shared-proto 给 `AgoraEgressConfig` 加
   `app_id`,driveningress / egress 透传。
2. **前端**:egress 在 Agora 里发的"视频轨"不是画面,是黑帧 + SEI 里的动画数据(和 LiveKit 路由一样要客户端渲染)。
   TEN 自带的 playground 用 Agora Web SDK 直接播视频,看到的是黑屏。需要 Web SDK 的 Agora 路由
   (订阅形象 uid 的音频 + 读 SEI 动画,喂宿主模式播放器),目前 Web SDK 只有 LiveKit 路由。

## 开发

```bash
pip install -e ../../..            # spatialreal(本仓库)
pip install agora-token-builder pytest pytest-asyncio
python3 -m pytest tests -q         # 桥接逻辑:分句、空闲收尾、flush、重连(不需要 ten_runtime)
```
