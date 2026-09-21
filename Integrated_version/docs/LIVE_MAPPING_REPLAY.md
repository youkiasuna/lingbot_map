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

這樣設計是為了先把局部點雲與融合介面測穩，再接入實際深度推論後端。

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
  --max-frames 43
```

若 `predictions.npz` 位於其他 mapping archive，請使用實際路徑。必須確保它與對應的 preprocessed images、world_points、frame_paths 來自同一次 mapping run。

查看結果：

```bash
cat outputs/runtime/live_mapping_replay_test/replay_summary.json
cat outputs/runtime/live_mapping_replay_test/live_map.json
```

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

下一步才將 `PredictionPointCloudReplay` 替換或擴充為真正的 RGB/depth backend：

1. 以滑動視窗輸入 LingBot-MAP。
2. 取得局部 depth/world points。
3. 依 pose 對齊到 live map。
4. 呼叫 `IncrementalVoxelMap.update()`。
5. 將 map version 發布給 Viewer。

目前 RTSP、手機影像、真正 online depth inference 與實車控制仍為 `NOT VERIFIED`。
