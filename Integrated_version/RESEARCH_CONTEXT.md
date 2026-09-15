# LingBot-MAP 視覺定位研究背景

請將以下內容視為目前研究專案的固定背景。後續討論、修改程式與實驗設計都應以此為基準。

## 1. 研究目標

本研究目前不使用實車，先在模擬與離線資料上完成視覺定位系統。

主要目標是：

```text
先建立 3D 地圖
→ 給定一張新的 RGB query image
→ 判斷相機目前在 3D 地圖中的位置與 yaw
→ 將定位相機位置顯示在彩色 3D 點雲網站
→ 將接受的 pose 提供給後續導航/A* 模擬
```

研究重點不是只做出展示，而是比較不同定位方法的準確度、穩定性與速度。

## 2. 主要資料

原始資料：

```text
data/frames/20260818_frames/
```

共有 2127 張影像。

正式 split：

```text
mapping: 000000, 000050, 000100, ...
query:   000025, 000075, 000125, ...
```

目前共有：

```text
43 張 mapping images
43 張 query images
```

split 由以下程式建立：

```text
Integrated_version/experiments/prepare_frame_split.py
```

目前主要重建資料包：

```text
outputs/scenes/scene_20260818/
```

## 3. 3D mapping 建立方式

使用 LingBot-MAP 模型建立 mapping：

```text
models/lingbot-map.pt
```

執行 wrapper：

```text
Integrated_version/experiments/run_lingbot_mapping.py
```

新的 mapping package：

```text
scene_20260818/mapping/
├── predictions.npz
├── predictions.json
├── run.json
├── preprocessed/*.png
└── rebuilt_colored_map.ply
```

`predictions.npz` 是定位真正使用的 archive，包含：

```text
extrinsic_c2w: 每個 mapping frame 的 camera-to-world pose
intrinsic: 相機內參
world_points: 每個 mapping pixel 對應的 3D world point
depth: 深度
depth_conf: 深度信心度
frame_paths: frame 對應的原始影像路徑
```

重要對齊規則：

```text
predictions.npz 必須和同一次 mapping 的 preprocessed/*.png 配對。
rebuilt_colored_map.ply 必須和同一次 mapping 的 predictions.npz 使用同一座標系。
```

## 4. 座標系約定

目前 20260818 正確的展示座標約定是：

```text
LingBot reconstruction coordinate
Y 軸負方向為向上，也就是 -Y-up
```

目前正確的彩色點雲來源：

```text
outputs/scenes/scene_20260818/mapping/rebuilt_colored_map.ply
```

高度著色 viewer 必須使用：

```text
--up-axis=-y
```

不要在 query pose 已經使用原始 LingBot 座標時，另外把 PLY 自動旋轉成另一個座標系，否則點雲與相機 marker 會不一致。

## 5. 方法一：ORB + PnP baseline

程式：

```text
Integrated_version/experiments/orb_keyframe_localizer.py
```

流程：

```text
query RGB image
→ resize 到 LingBot mapping 尺寸 518x294
→ ORB feature extraction
→ mapping preprocessed images 做 Hamming matching
→ 從 matching keypoint 查詢 predictions.npz 的 world_points
→ 2D query point / 3D world point correspondence
→ solvePnPRansac
→ position_xyz、yaw、confidence
```

目前 ORB 參數基準：

```text
max_features: 2000
ratio: 0.75
top_k: 5
min_matches: 25
min_inliers: 12
reprojection_error_px: 5.0
```

目前重新建立的 43 張 query 結果：

```text
成功定位：41 / 43
定位成功率：95.35%
```

ORB 結果輸出：

```text
scene_20260818/results/orb/summary.json
```

## 6. 方法二：彩色 3D 點雲投影方案 A

程式：

```text
Integrated_version/experiments/colored_pointcloud_localizer.py
```

這不是直接把 2D 照片和 3D 點做一對一比對，而是：

```text
彩色 rebuilt_colored_map.ply
→ 使用 mapping camera pose 從 3D 點雲投影出 virtual RGB view
→ query image 與 virtual RGB view 做 ORB retrieval
→ virtual view 的 pixel-to-point buffer 提供 2D/3D 對應
→ solvePnPRansac
→ position_xyz、yaw、confidence
```

方案 A 的重要條件：

```text
PLY 和 predictions.npz 必須來自同一次 mapping。
不可直接使用 floor_calibrated.ply，除非同步轉換 predictions.npz 的 pose/world_points。
```

目前結果：

```text
同一次 mapping 的第一張 query 可以成功定位。
IMG_1280.png 目前為 low_confidence，沒有可靠的 3D pose。
```

方案 A 目前仍有工程限制：

```text
每張 query 會重新讀取/投影 PLY。
目前單張約需數十秒。
下一步應快取所有 virtual views 和 pixel-to-point buffers。
```

## 7. 外部照片 IMG_1280 的現況

外部 query：

```text
outputs/scenes/scene_20260818/external_query_images/IMG_1280.png
```

照片尺寸：

```text
4032x3024，直式照片
```

mapping image 尺寸：

```text
518x294，橫式影像
```

目前程式直接 resize，會造成影像比例變形。因此 IMG_1280 的定位結果不可靠。

ORB 暫定最佳候選：

```text
best frame: 14
position_xyz: [0.06501, -0.08004, 0.86628]
yaw_deg: 12.58
matches: 26
inliers: 11
confidence: 0.5043
status: low_confidence
```

其他候選位置差異很大，所以不能把這個位置當成正式 ground truth。

下一步要先處理：

```text
直式照片旋轉判斷
保持 aspect ratio
letterbox 或 center crop
query camera intrinsic 修正
```

## 8. Viewer 展示

height-colored 3D map：

```text
scene_20260818/visualization/auto_floor_viewer.html
```

ORB + PnP viewer：

```text
scene_20260818/external_1280/orb_viewer.html
```

彩色點雲定位 viewer：

```text
scene_20260818/external_1280/colored_viewer.html
```

Viewer 目前支援：

```text
總覽
定位相機：移動到估計 position，並使用 yaw 對準方向
符合影像視角：切換到最佳 mapping camera 的拍攝方向
左上角工具列收合/展開
```

所有 viewer 都應使用 `-Y-up`，否則會出現上下顛倒或 marker 與點雲不一致。

## 9. 目前研究比較方式

ORB baseline 和彩色 3D 點雲方案 A 必須使用：

```text
同一份 mapping archive
同一批 query images
同一相機內參
同一座標系
同一 confidence gate
```

主要指標：

```text
定位成功率
平均/median/P95 位置誤差
yaw 誤差
平均與 P95 latency
match_count
inlier_count
inlier_ratio
reprojection_error_px
錯誤接受率
low_confidence / lost 比例
```

目前還缺少真正的 ground truth。LingBot 的 reconstruction pose 只能當作 pseudo ground truth 或內部一致性檢查，不能直接宣稱是真實世界位置誤差。

正式研究應加入：

```text
AprilTag/ArUco 量測
人工量測位置
motion capture
或其他外部定位 ground truth
```

## 10. 主要研究問題

目前研究問題可寫成：

> 在相同的 LingBot-MAP 3D reconstruction 與 query split 下，直接使用 mapping image 的 ORB + PnP，和使用彩色 3D 點雲投影 virtual views 的定位方法，哪一個在位置誤差、yaw 誤差、成功率、錯誤拒絕能力與推論時間上較好？

## 11. 一鍵 pipeline

主要入口：

```text
Integrated_version/experiments/run_research_pipeline.py
```

完整執行：

```bash
cd /media/ee303/1tb/lingbot_map
/home/ee303/miniconda3/envs/lingbot-map/bin/python \
  Integrated_version/experiments/run_research_pipeline.py
```

主要 stages：

```text
split
mapping
orb
viewer
colored
```

Pipeline 預設會重用已存在的輸出。若要強制重跑，加上：

```text
--rerun
```

## 12. 下一步優先順序

1. 統一 ORB 與彩色方案 A 的 JSON/JSONL 輸出格式。
2. 修正外部照片 aspect ratio、旋轉與 camera intrinsic。
3. 快取彩色 PLY 的 virtual views，降低方案 A latency。
4. 對同一批 43 張 query 完成兩方法比較。
5. 加入 ground truth 與正式位置/yaw 誤差。
6. 加入 SuperPoint/LightGlue 作為更強特徵方法。
7. 加入 temporal filtering 與 confidence gate。
8. 將 accepted pose 接到 A*，比較定位錯誤對導航成功率的影響。

## 給後續 ChatGPT 的工作原則

```text
所有修改只放在 Integrated_version。
不要刪除或覆蓋既有研究結果，除非使用者明確要求。
先確認 PLY、predictions.npz、preprocessed images 是否來自同一次 mapping。
20260818 展示座標固定使用 -Y-up。
不要把 low_confidence 結果當成成功定位。
不要把 LingBot reconstruction coordinate 當成真實公尺 ground truth。
比較方法時必須固定 query split、mapping package、camera calibration 和 confidence threshold。
```
