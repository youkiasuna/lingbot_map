# 影片 Replay：局部點雲與增量融合

## 目的

這個模組先用既有 LingBot-MAP 的 `predictions.npz`，依照 frame 順序模擬：

影片 frame window
→ 局部 world points
→ sliding-window replay
→ voxel fusion
→ live map version

它可以先驗證資料流、座標一致性、地圖版本與融合效能，不會覆蓋正式 mapping 結果。

## 重要限制

目前 replay 使用既有 `world_points`，不是每個新 RGB frame 重新執行 LingBot-MAP depth inference。因此它是：

`incremental map fusion replay`

不是：

`true online monocular 3D reconstruction`

這樣設計是為了先把局部點雲與融合介面測穩，再接入實際深度推論後端。所有 backend 都應回傳 `LocalPointCloudResult`，因此 replay、LingBot-MAP inference 與未來 RTSP backend 可以共用同一個 fusion runner。

## 執行

先確認 mapping package：

```bash
find outputs/scenes/scene_20260818 -name predictions.npz -print
```

執行短 replay：

```bash
PYTHONPATH=Integrated_version \
python Integrated_version/experiments/run_live_mapping_replay.py \
  --mapping-package outputs/scenes/scene_20260818/mapping/predictions.npz \
  --output-dir outputs/runtime/live_mapping_replay_test \
  --window-size 10 \
  --process-every 5 \
  --max-frames 43 \\
  --benchmark-label baseline
```

若 `predictions.npz` 位於其他 mapping archive，請使用實際路徑。必須確保它與對應的 preprocessed images、world_points、frame_paths 來自同一次 mapping run。

查看結果：

```bash
cat outputs/runtime/live_mapping_replay_test/replay_summary.json
cat outputs/runtime/live_mapping_replay_test/live_map.json
```

## Benchmark 與資料累積監測

runner 現在會記錄：

- `latency_mean_ms`
- `latency_p50_ms`
- `latency_p95_ms`
- `peak_rss_mb`
- `final_output_bytes`（目前主要為 binary `live_points.npz` 與 metadata）
- `final_voxel_count`
- `pointcloud_file`
- 每次 update 的 `rss_mb`、`output_bytes`、`voxel_count`

可執行長一點的 replay：

```bash
rm -rf outputs/runtime/live_mapping_benchmark
PYTHONPATH=Integrated_version \\
python Integrated_version/experiments/run_live_mapping_replay.py \\
  --mapping-package outputs/scenes/scene_20260818/mapping/predictions.npz \\
  --output-dir outputs/runtime/live_mapping_benchmark \\
  --window-size 10 \\
  --process-every 1 \\
  --max-frames 43 \\
  --benchmark-label stress_process_every_1
```

查看 benchmark：

```bash
python -m json.tool outputs/runtime/live_mapping_benchmark/replay_summary.json
```

判斷方式：

- `peak_rss_mb` 長時間近似穩定：沒有明顯 RAM 累積證據。
- `final_output_bytes` 只包含固定輸出檔案：沒有逐 update 檔案堆積。
- `final_voxel_count` 不超過 `--max-points`：voxel map 有上限。
- `latency_p95_ms` 持續上升：地圖融合或序列化成本正在惡化。

目前預設使用壓縮 binary `live_points.npz`，避免每次將完整點雲序列化成 JSON；若舊 Viewer 仍需要 JSON，可建立 `LiveMapManager(..., publish_json_points=True)` 暫時輸出 `live_points.json`。這些是資源監測指標，不等同於已完成 RTSP 或 GPU online inference。

## 觀察指標

- `map_version`
- `input_points`
- `fused_points`
- `latency_ms`
- `total_latency_ms`
- `window_size`
- `process_every`

如果融合 latency 沒有隨 map version 線性增加，代表 bounded voxel fusion 的方向合理。

## 後續接入

目前 runner 已透過 `runtime/local_pointcloud_backend.py` 的 `PredictionNpzBackend` 取得局部點雲，也支援 `LingBotMapBackend` 的離線 windowed inference。

1. 使用 `--backend lingbot` 以單一 window 測量真正 LingBot-MAP inference。
2. 確認局部 `predictions.npz` 與 `world_points` 輸出。
3. 記錄 inference、點雲與 fusion latency。
4. 呼叫 `IncrementalVoxelMap.update()`。
5. 將 map version 發布給 Viewer。

目前 RTSP、手機影像、真正 online depth inference 與實車控制仍為 `NOT VERIFIED`。
\n## LingBot-MAP backend 單一 window 測試\n\n這個測試會實際呼叫現有 `run_lingbot_mapping.py`，請先只執行一個 window：\n\n```bash\nPYTHONPATH=Integrated_version \\\npython Integrated_version/experiments/run_live_mapping_replay.py \\\n  --backend lingbot \\\n  --source-dir data/frames/20260818_frames \\\n  --model-path models/lingbot-map.pt \\\n  --lingbot-root lingbot-map-main \\\n  --output-dir outputs/runtime/live_mapping_lingbot_test \\\n  --window-size 10 \\\n  --process-every 10 \\\n  --max-frames 10 \\\n  --max-windows 1 \\\n  --benchmark-label lingbot_single_window\n```\n\n這會使用 GPU 與產生局部 mapping package；實際 inference latency、GPU memory 與輸出是否成功必須在 RTX 3090 主機測試，目前為 `NOT VERIFIED`。\n