# Map Localization Test

這個資料夾是獨立的定位測試區，不會修改 `lingbot-map-main` 或 `car`。

目前包含兩個可直接測試的階段：

1. 將 `.ply` 點雲投影成 2D 俯視地圖（`map.pgm`）及座標設定檔（`map.json`）。
2. 以終端機模擬車子啟動定位與移動，確認 `x`、`y`、`yaw` 能正確寫入 `current_pose.json`。

## 快速測試

在專案根目錄執行：

```bash
python map_localization_test/build_topdown_map.py \
  --ply map_localization_test/samples/room_ascii.ply \
  --output-dir /tmp/lingbot_topomap

python map_localization_test/mock_pose_tracker.py \
  --map-json /tmp/lingbot_topomap/map.json
```

第二個程式啟動後可輸入：

- `f`：前進
- `b`：後退
- `l`：左轉
- `r`：右轉
- `p`：列印目前座標
- `q`：結束

每次更新都會寫入 `/tmp/lingbot_topomap/current_pose.json`。這是測試座標系與後續網頁地圖串接的工具，**不會**從影像做真實定位。

## 使用你的 PLY

```bash
python map_localization_test/build_topdown_map.py \
  --ply /path/to/your_map.ply \
  --output-dir /path/to/output_map \
  --up-axis z \
  --meters-per-pixel 0.05
```

`--up-axis` 是點雲的垂直方向。若產生的俯視地圖看起來側躺，依序嘗試 `z`、`y`、`x`。

輸出的 `map.json` 定義世界座標與影像像素座標的轉換，之後影像定位器會使用同一份設定。


## 從影片生成 PLY 到後續流程

目前建議流程是：

```text
videos/*.mp4
  -> LingBot-MAP demo.py 產生 dense PLY
  -> build_topdown_map.py 投影成 map.pgm + map.json
  -> mock_pose_tracker.py 測試座標系
  -> 後續接真實影像定位 / 車控網頁
```

### 1. 影片轉高細節 PLY

已驗證可用的高細節參數如下。因為目前環境沒有 FlashInfer，所以要加 `--use_sdpa`；`lingbot-map.pt` checkpoint 與 `--image_size 518` 相容，不能直接升到 672。

```bash
/home/ee303/miniconda3/envs/lingbot-map/bin/python lingbot-map-main/demo.py \
  --model_path lingbot-map-main/checkpoints/lingbot-map.pt \
  --image_folder videos/20260804_frames \
  --image_size 518 \
  --camera_num_iterations 4 \
  --offload_to_cpu \
  --use_sdpa \
  --downsample_factor 1 \
  --conf_threshold 1.0 \
  --output_ply map_localization_test/outputs/20260804_dense.ply
```

目前輸出結果：

- `map_localization_test/outputs/20260804_dense.ply`
- 約 `50,865,528` points
- 約 `922M`

參數取捨：

- `--downsample_factor 1`：保留最多點，最細緻，但 PLY 很大。
- `--conf_threshold 1.0`：保留較多低 confidence 點；若雜點太多，可試 `1.5` 或 `2.0`。
- `--image_size 518`：目前 checkpoint 相容解析度。
- `--fps 30` / 直接用 `videos/20260804_frames`：保留完整 334 frames。

如果要重新從影片抽 frame，可以改用 `--video_path videos/20260804.mp4 --fps 30`；第一次已經產生 `videos/20260804_frames` 後，後續直接用 `--image_folder` 比較快。

### 2. 快速確認 PLY 可讀

先讀少量點，避免一開始就處理完整 922M 檔案：

```bash
python3 map_localization_test/build_topdown_map.py \
  --ply map_localization_test/outputs/20260804_dense.ply \
  --output-dir /tmp/lingbot_dense_map_check \
  --max-points 1000
```

若看到 `Read 1000 vertices` 和 `Wrote ... map`，代表 PLY 格式可以進入後續流程。

### 3. PLY 轉 PGM 地圖

確認可讀後，再產生正式 2D 地圖：

```bash
python3 map_localization_test/build_topdown_map.py \
  --ply map_localization_test/outputs/20260804_dense.ply \
  --output-dir map_localization_test/outputs/20260804_map \
  --up-axis z \
  --meters-per-pixel 0.05 \
  --padding-m 0.5 \
  --min-points-per-pixel 2
```

輸出會有：

- `map_localization_test/outputs/20260804_map/map.pgm`
- `map_localization_test/outputs/20260804_map/map.json`

調參方式：

- 地圖太大或太慢：把 `--meters-per-pixel` 調大，例如 `0.10`。
- 地圖太稀疏：把 `--min-points-per-pixel` 調回 `1`。
- 雜點太多：回到 PLY 生成階段提高 `--conf_threshold`，或轉 PGM 時提高 `--min-points-per-pixel`。
- 地圖方向怪：依序試 `--up-axis z`、`--up-axis y`、`--up-axis x`。

### 4. 測試座標系與車子位姿輸出

PGM 和 `map.json` 產生後，用 mock tracker 先確認座標更新流程：

```bash
python3 map_localization_test/mock_pose_tracker.py \
  --map-json map_localization_test/outputs/20260804_map/map.json
```

互動指令：

- `f`：前進
- `b`：後退
- `l`：左轉
- `r`：右轉
- `p`：列印目前座標
- `q`：結束

每次更新會寫到：

```text
map_localization_test/outputs/20260804_map/current_pose.json
```

### 5. 後續真正定位要補的資料

PLY/PGM 只能建立地圖底圖。若要讓車子「知道自己在哪裡」，還需要影像定位資料庫：

- 建圖影片抽出的 database images。
- 每張 database image 的相機位姿。
- 車載相機內參。
- 即時影像定位器，把目前 camera frame 對到 database/map 座標。

下一步實作順序建議：

1. 確認 `map.pgm` 方向和比例正確。
2. 把 `current_pose.json` 接到網頁或車控 UI 顯示。
3. 加入真實定位器，取代 `mock_pose_tracker.py`。
4. 用定位器持續更新 `current_pose.json`。


## 前端航點與 A* 規劃測試

產生 `map.pgm` / `map.json` 後，可以啟動本地網頁 UI：

```bash
python3 map_localization_test/web_server.py \
  --map-dir map_localization_test/outputs/20260804_map \
  --port 18088
```

瀏覽器打開：

```text
http://127.0.0.1:18088
```

使用方式：

- 先讓 `mock_pose_tracker.py` 或未來的真實定位器持續寫入 `current_pose.json`。
- 在地圖上點選 Goal。
- 後端會以 `current_pose.json` 的位置作為 Start，執行 A*，並把結果寫入 `planned_path.json`。
- 按 `Start` 會把 `navigation_state.json` 設成 `NAVIGATING`；目前只建立狀態，不會送馬達命令。
- 按 `Stop` 會把狀態設成 `STOP`。

也可以不用網頁，直接用 CLI 測試 A*：

```bash
python3 map_localization_test/grid_navigation.py \
  --map-dir map_localization_test/outputs/20260804_map \
  --goal-x 2.35 \
  --goal-y 1.80
```

如果地圖的 unknown 區域太多，測試時可加 `--allow-unknown`；正式導航建議先不要讓車規劃穿越 unknown cell。

## 下一階段：真實影像定位

要讓相機在啟動時找到自己、並在行駛中修正位置，除了 `.ply` 還需要：

- 資料庫照片。
- 每張照片的相機位姿，建議使用 COLMAP 的 `cameras.bin`、`images.bin`、`points3D.bin`。
- 車載相機的內參與安裝姿態。

取得這些資料後，會在此資料夾加入 `build_database.py`、`global_localizer.py`、`visual_odometry.py` 與 `live_localization.py`。
