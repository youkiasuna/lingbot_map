# RTSP Online Navigation 雛形

## 目的

本雛形將 RTSP camera、latest-frame queue、ORB localization、PoseGate、NavigationManager、LiveViewerState 與 dry-run command 串接。

流程：

RTSP -> bounded latest-frame queue -> ORB localization -> PoseGate -> NavigationManager -> live pose/status/path -> dry-run safety command

## 執行

```bash
PYTHONPATH=Integrated_version \
python Integrated_version/runtime/online_mapping_navigation.py \
  --mapping-dir outputs/scenes/scene_20260818/mapping \
  --url rtsp://CAMERA_IP:8554/live \
  --max-frames 30 \
  --queue-size 1
```

目前永遠是 dry-run，不會啟動 ESP32 馬達。

## 重要指標

- processed_frames
- dropped_frames
- processing_fps
- frame_age_ms
- localization_status
- mode
- command

若 dropped_frames 增加，代表 camera 輸入速度高於 ORB 處理速度；bounded queue 會丟棄舊 frame，避免延遲越積越大。

## 輸出

outputs/runtime/online_navigation/ 會包含 live_pose.json、live_path.json、live_status.json。

## 限制

- 尚未接入 LingBot-MAP background local mapping。
- 不代表 ORB localization 已成功；confidence 不足時會 safety stop。
- RTSP 必須先能連線。
- 實際 ESP32 與車輛控制保持停用。
