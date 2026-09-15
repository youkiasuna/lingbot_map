# 視覺重定位實驗 Baseline

這份 baseline 的目的不是直接控制車子，而是在一張已建立的 LingBot 3D 地圖中，使用單目查詢影像輸出可驗證的相機 pose 與 confidence。所有後續方法都必須使用相同的資料切分、相機座標約定與評估輸出。

## 一鍵執行研究流程

建議從 repository root 執行：

```bash
/home/ee303/miniconda3/envs/lingbot-map/bin/python \
  Integrated_version/experiments/run_research_pipeline.py
```

預設流程為：

```text
原始 frames
  -> split（mapping 取每 50 張，query 取中間 frame）
  -> LingBot-MAP mapping
  -> 同一次 mapping 輸出的彩色 PLY
  -> ORB + PnP 全部 query
  -> 20260818 固定 -Y-up 的高度著色 3D viewer
  -> 彩色點雲投影方案 A（預設 1 張 smoke test）
```

輸出預設放在 `outputs/scenes/scene_20260818/`。輸入連結指向 `data/scenes/` 與 `data/frames/`。流程會重用已存在的輸出，
只有指定 `--rerun` 才會重跑該階段。常用操作：

```bash
# 只重跑 ORB 與 3D viewer
/home/ee303/miniconda3/envs/lingbot-map/bin/python \\
  Integrated_version/experiments/run_research_pipeline.py \\
  --scene-dir outputs/scenes/scene_20260818 \\
  --stages orb,viewer

# 彩色方案 A 跑全部 query（目前每張會重新讀取/投影 PLY，速度較慢）
/home/ee303/miniconda3/envs/lingbot-map/bin/python \\
  Integrated_version/experiments/run_research_pipeline.py \\
  --scene-dir outputs/scenes/scene_20260818 \\
  --stages colored --colored-limit 43
```

## 實驗資料結構

```text
outputs/scenes/<scene_id>/
  mapping/
    preprocessed/             # LingBot 輸入尺寸；000000.png 對應 archive frame 0
    predictions.npz           # 相機 pose、內參、3D world points、confidence
    predictions.json          # archive metadata 與座標說明
    run.json                  # 建圖模型與執行參數
  queries/
    images/                   # 與 mapping 不同時間拍攝的查詢影像
    ground_truth.jsonl        # 評估時使用；不可由 query image 本身推得
  configs/
    baseline_config.json
  results/
    <method_name>/
      localization.jsonl
      metrics.json
```

`mapping/preprocessed` 與 `predictions.npz` 必須使用同一次 LingBot-MAP 執行產生。archive 裡的 `world_points[frame, y, x]` 才能和該 preprocessed image 的像素 `(x, y)` 對應。

## M0：建立可重複的 3D 地圖資料包

從 repository root 執行：

```bash
/home/ee303/miniconda3/envs/lingbot-map/bin/python \
  Integrated_version/experiments/run_lingbot_mapping.py \
  --image-folder /path/to/mapping_images \
  --model-path /path/to/lingbot-map.pt \
  --output-dir /path/to/experiments/scene_01/mapping \
  --output-ply /path/to/experiments/scene_01/mapping/map.ply
```

`run_lingbot_mapping.py` 位於 `Integrated_version/`，不會修改 LingBot-MAP 原始碼。它建立的 archive 包含：

- `extrinsic_c2w`: 每幀 OpenCV camera-to-world 外參，形狀 `(N, 3, 4)`。
- `intrinsic`: 每幀對應 preprocessed image 的內參，形狀 `(N, 3, 3)`。
- `world_points`: 每個 reference pixel 對應的世界座標。
- `world_points_conf`、`depth`、`depth_conf`: 可用於過濾不可靠的 3D 對應。
- `frame_paths`: 和 archive frame index 對齊的原始影像清單。schema 2 使用相對於 NPZ 所在目錄的路徑；舊 schema 1 使用絕對路徑。

注意：LingBot 預測 pose 可作為 baseline 的 pseudo ground truth 與資料庫座標，但不能直接宣稱是真實世界 ground truth。正式位置與 yaw 誤差應以量測位置、AprilTag、motion capture，或有外部 ground truth 的資料集評估。

## M1：固定 ORB + PnP baseline

第一個可比較方法固定為：

```text
query image
  -> reference image retrieval
  -> ORB feature matching
  -> reference keypoint 查詢 world_points[y, x]
  -> query 2D / map 3D correspondences
  -> solvePnPRansac
  -> reprojection refinement
  -> pose + inlier_count + reprojection_error + confidence
```

Reference database 只能使用 mapping frames。query 必須來自另一趟重訪影片，或至少在建庫時完全排除的 frame；不可用同一張 query image 的 descriptor 或 3D points 建立資料庫。

目前 `orb_keyframe_localizer.py` 已提供第一版 demo localizer：

```bash
/home/ee303/miniconda3/envs/lingbot-map/bin/python \
  Integrated_version/experiments/orb_keyframe_localizer.py \
  --mapping-dir outputs/runs/20260818_smoke \
  --query-image outputs/runs/20260818_smoke/preprocessed/000000.png \
  --output-json outputs/runs/20260818_smoke/orb_demo_result.json \
  --pose-file outputs/runs/20260818_smoke/current_pose.json \
  --frame-stride 1 \
  --top-k 5 \
  --min-matches 8 \
  --min-inliers 4
```

輸出分成兩份：

- `orb_demo_result.json`: 完整實驗結果，包含 top-K keyframe、match count、PnP inliers、reprojection error、confidence 與 latency。
- `current_pose.json`: Web / navigation demo 讀取的最新 pose，符合 `PoseSample` schema。

第一版 demo 的座標仍是 LingBot reconstruction coordinate，尚未做真實比例尺校正。為了先讓導航端可以接資料，`current_pose.json` 暫時使用 `position_xyz[0]` 作為 `x_m`、`position_xyz[2]` 作為 `y_m`。

正式 `20260818` demo split 可用下面方式建立：

```bash
/home/ee303/miniconda3/envs/lingbot-map/bin/python \
  Integrated_version/experiments/prepare_frame_split.py \
  --source-dir data/frames/20260818_frames \
  --scene-dir outputs/scenes/scene_20260818 \
  --mapping-step 50 \
  --query-step 50 \
  --query-offset 25
```

這會產生 `43` 張 mapping frames 與 `43` 張 query images。mapping 用 `000000, 000050, 000100...`，query 用中間的 `000025, 000075, 000125...`。

建立 20260818 demo mapping package：

```bash
/home/ee303/miniconda3/envs/lingbot-map/bin/python \
  Integrated_version/experiments/run_lingbot_mapping.py \
  --image-folder outputs/scenes/scene_20260818/inputs/mapping_frames \
  --model-path models/lingbot-map.pt \
  --output-dir outputs/scenes/scene_20260818/mapping \
  --camera-num-iterations 1 \
  --use-sdpa
```

若要把 query image 的相機位置直接顯示在 3D map 中，可執行：

```bash
/home/ee303/miniconda3/envs/lingbot-map/bin/python \
  Integrated_version/experiments/localize_query_in_3d_viewer.py \
  --mapping-dir outputs/scenes/scene_20260818/mapping \
  --query-image outputs/scenes/scene_20260818/inputs/query_images/000020.jpg \
  --output-html outputs/scenes/scene_20260818/demo_query_000020_viewer.html \
  --output-json outputs/scenes/scene_20260818/demo_query_000020_result.json \
  --pose-file outputs/scenes/scene_20260818/current_pose.json \
  --frame-stride 1 \
  --top-k 5
```

HTML viewer 會顯示：

- 3D map points。
- mapping camera centers。
- best matched keyframe。
- query camera pose。

這個 viewer 是 demo 輸出端，不是評估工具。正式實驗仍應使用 `query_camera_result.json` 或 JSONL results 做指標統計。

若要分析你自己另外拍的照片，請放到：

```text
outputs/scenes/scene_20260818/external_query_images/
```

然後執行：

```bash
/home/ee303/miniconda3/envs/lingbot-map/bin/python \
  Integrated_version/experiments/analyze_external_queries.py
```

輸出會放在：

```text
outputs/scenes/scene_20260818/external_query_results/
```

每張 query image 會產生一份 `*_result.json` 與一份 `*_viewer.html`，總表會寫到 `summary.json`。

## M2：彩色 3D 點雲投影 baseline（方案 A）

這個方法不是直接拿 2D 照片和 PLY 做一對一特徵比對，而是把彩色 PLY 從每個
mapping camera pose 投影成虛擬 RGB view。query image 先和虛擬 view 做 ORB
retrieval，再由虛擬 view 的 pixel-to-point buffer 建立 2D/3D correspondences，
最後使用相同的 PnP-RANSAC 與 confidence gate。

`predictions.npz` 是 LingBot reconstruction 座標，因此必須使用同一座標系的原始
彩色 PLY；不可直接使用 `floor_calibrated.ply`，除非同步把 archive 的 pose 與
world points 套用相同校正矩陣。

單張 query 測試：

```bash
/home/ee303/miniconda3/envs/lingbot-map/bin/python \\
  Integrated_version/experiments/colored_pointcloud_localizer.py \\
  --ply outputs/maps/20260818_dense.ply \\
  --mapping-dir outputs/scenes/scene_20260818/mapping \\
  --query-image outputs/scenes/scene_20260818/external_query_images/IMG_1280.png \\
  --output-json outputs/scenes/scene_20260818/external_query_results/IMG_1280_colored_result.json \\
  --output-html outputs/scenes/scene_20260818/external_query_results/IMG_1280_colored_viewer.html
```

正式比較時固定相同的 query split、`min_matches=25`、`min_inliers=12`，並將本方法
與 `orb_keyframe_pnp` 的成功率、位置誤差、yaw 誤差與 latency 放在同一張表。

## 統一輸出契約

每一個定位方法都寫出 JSONL，一張 query image 一列：

```json
{
  "query_id": "000123",
  "method": "orb_pnp",
  "status": "localized",
  "timestamp_unix": 0.0,
  "position_m": [0.0, 0.0, 0.0],
  "yaw_deg": 0.0,
  "confidence": 0.0,
  "retrieval_rank": 1,
  "match_count": 0,
  "inlier_count": 0,
  "reprojection_error_px": 0.0,
  "latency_ms": 0.0
}
```

`status` 只可為 `localized`、`low_confidence`、`lost` 或 `invalid_input`。Confidence gate 只改變接受或拒絕 pose 的規則，不可改動同一張影像的原始定位結果。

## 固定比較條件

- 同一批 mapping images、query images、camera calibration、reference/query split。
- ORB、SuperPoint 或其他方法都輸出相同 JSONL schema。
- PnP RANSAC 閾值、最大特徵數、top-k retrieval 與 confidence 門檻寫入 config。
- 第一輪只比較定位；A* 模擬只讀取已接受的 pose，作為第二階段實驗。

## 指標與順序

1. Retrieval recall@K、定位成功率、位置誤差、yaw 誤差、latency。
2. 固定定位器後，做 confidence threshold sweep，量測接受率、錯誤接受率與 LOST/LOW_CONFIDENCE 比例。
3. 將同一批 accepted poses 輸入普通 A* 與距離場 A* 模擬，量測路徑長度、最小障礙距離、碰撞率與到達率。
4. 只替換一項元件：ORB vs SuperPoint，或不同 retrieval 方法。其餘設定固定。
