# Runtime 模組

負責把影像來源、建圖 backend、定位、規劃與 viewer state 按生命週期串起來。演算法本身應留在 `map/`、`localization/`、`planner/`；HTTP 與頁面留在 `web/`。

- `frame_queue.py`、`streaming_mapping_worker.py`：影像佇列與背景工作。
- `lingbot_map_backend.py`、`local_pointcloud_backend.py`：建圖 backend。
- `lingbot_map_integration.py`：上游 LingBot-MAP 載入、預處理影像輸出與 frame-aligned prediction archive 契約。
- `lingbot_map_session.py`：常駐載入 LingBot-MAP 模型並重複執行影像資料夾推論。
- `incremental_map_fusion.py`、`live_map_manager.py`：地圖融合、版本與發布。
- `live_viewer_state.py`：整理 viewer 所需的點雲、姿態、路徑與狀態輸出。
- `mapping_state_machine.py`、`navigation_manager.py`：狀態與流程協調。
- `live_pointcloud_runtime.py`：持續擷取與增量點雲建圖的流程協調；不含定位、路徑規劃或馬達控制。
- `online_mapping_navigation.py`：RTSP 最新幀定位 dry-run，不等同 A* 導航流程。
- `realtime_navigation.py`：串接 ORB 重定位、A* 與 Pure Pursuit；目前 ESP32 馬達輸出仍停用。
- `local_pointcloud_replay.py`：離線重播，不代表即時模型推論。
- `video_source.py`：統一將 camera index 字串轉成 OpenCV 裝置索引。

系統狀態與限制見 [live mapping architecture](../docs/LIVE_MAPPING_ARCHITECTURE.md)。

## 驗證

```powershell
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_live_mapping_architecture.py" -v
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_live_pointcloud_runtime.py" -v
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_online_mapping_navigation.py" -v
```
