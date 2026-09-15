# 整合版

這個資料夾整理了目前可運作的地圖生成 + 姿態提供 + 網頁介面 + 路徑規劃的第一版整合流程。

## 優先順序

1. 地圖流程
   - map/build_topdown_map.py
2. 姿態契約
   - localization/mock_pose_tracker.py
3. 網頁介面
   - web/server.py
   - web/index.html
   - web/app.js
   - web/styles.css
4. 路徑規劃
   - planner/grid_navigation.py
5. 障礙物距離場
   - map/build_obstacle_distance.py
6. 點雲品質整理
   - map/clean_point_cloud_20260818.py
7. 3D 可導航地圖
   - map/build_3d_navigation_map.py

## 這一階段的目標

在保留目前可執行流程的前提下，把各個模組整理到同一個整合層中。
目前的核心目標是讓流程：

map -> current_pose -> web goal selection -> planned_path

能夠穩定跑起來，再進一步接上真實視覺定位或 ESP32 控制。

## 接下來的步驟

- 驗證地圖生成
- 驗證姿態 JSON 契約
- 驗證網頁 UI 與規劃器整合
- 產生每個地圖格到最近障礙物的距離
- 以障礙物距離 penalty 讓 A* 偏好較安全的地面區域
- 用 live localization 取代 mock pose
- 連接馬達控制器 / ESP32

## DDDMR perception 簡化版

目前先借用 DDDMR `dddmr_perception_3d` 的核心概念，不直接引入 ROS 2：

```text
map.pgm + map.json
   -> obstacle_distance.bin
   -> 每個可走格到最近障礙物的距離
   -> A* obstacle proximity penalty
   -> planned_path.json
```

產生距離場：

```bash
python3 Integrated_version/map/build_obstacle_distance.py \\
   --map-dir /tmp/lingbot_integrated_map
```

啟用風險感知規劃：

```bash
python3 Integrated_version/planner/grid_navigation.py \\
   --map-dir /tmp/lingbot_integrated_map \\
   --goal-x 1.28 \\
   --goal-y 0.16 \\
   --use-obstacle-distance \\
   --safety-radius-m 0.25 \\
   --risk-weight 1.0
```

未加 `--use-obstacle-distance` 時，仍使用原本的 A* 行為。距離場是軟性成本，並不會取代 occupied cell 的硬性禁止。

## 第一階段：20260818 點雲品質整理

這一階段只處理點雲品質，不判斷牆面、雜物或地板類別：

```text
20260818_dense.ply
   -> confidence filtering
   -> deterministic stride sampling
   -> 3 cm voxel merge
   -> isolated voxel removal
   -> 20260818_clean.ply
```

執行：

```bash
python3 Integrated_version/map/clean_point_cloud_20260818.py \\
   --ply outputs/maps/20260818_dense.ply \\
   --output-dir outputs/maps/20260818_clean \\
   --confidence-threshold 1.0 \\
   --voxel-size-m 0.03 \\
   --min-points-per-voxel 2 \\
   --max-input-points 5000000
```

輸出：

- `20260818_clean/20260818_clean.ply`
- `20260818_clean/cleaning_stats.json`
- `20260818_clean/20260818_clean_height_viewer.html`

目前實測約從 3.24 億個原始點整理成 121,231 個 voxel 點。座標約定為：20260818 使用 `-Y`，20260804 使用 `-Z`。下一階段再用清理後點雲做地板平面估計與 floor/obstacle/unknown 分類。

## 第三階段：建立 3D 可導航地圖

這一階段使用已完成地板 leveling 的點雲，將幾何資料轉成可導航資料：

```text
calibrated point cloud
   -> floor / obstacle / unknown PLY
   -> 2D occupancy projection
   -> robot-radius inflation
   -> obstacle distance field
   -> A* / risk-aware A*
```

分類規則目前是幾何規則，不宣稱能區分牆和家具的語意：

- 地板高度附近 `+/- 0.08 m`：floor
- 高於地板 `0.10` 到 `2.0 m`：obstacle
- 其他點：unknown
- obstacle 以車體半徑 `0.20 m` 膨脹後才進入 occupancy map

20260818（`-Y` 垂直）：

```bash
python3 Integrated_version/map/build_3d_navigation_map.py \\
   --ply outputs/maps/20260818_calibrated_y/20260818_floor_calibrated.ply \\
   --output-dir outputs/maps/20260818_navigation \\
   --vertical-axis=-y \\
   --resolution-m 0.05 \\
   --robot-radius-m 0.20
```

20260804（`-Z` 垂直）：

```bash
python3 Integrated_version/map/build_3d_navigation_map.py \\
   --ply outputs/maps/20260804_calibrated_z/20260804_floor_calibrated.ply \\
   --output-dir outputs/maps/20260804_navigation \\
   --vertical-axis=-z \\
   --resolution-m 0.05 \\
   --robot-radius-m 0.20
```

每份輸出包含：

- `floor.ply`
- `obstacle.ply`
- `unknown.ply`
- `map.pgm` / `map.json`
- `navigation_map.pgm` / `navigation_map.json`
- `obstacle_distance.bin` / `obstacle_distance.json`

實測結果：20260818 產生 `134x128` 地圖、5,242 個 free cells；20260804 產生 `60x31` 地圖、736 個 free cells。`map.pgm` 可直接交給現有 planner，`obstacle_distance.bin` 可搭配 `--use-obstacle-distance` 使用。

## 車子模型路徑模擬

目前先使用差速車的 unicycle 模型：

- 圓形車體 footprint，半徑預設 `0.20 m`
- 最大線速度預設 `0.15 m/s`
- 最大角速度預設 `0.7 rad/s`
- 大轉角時先原地旋轉，再向下一個 waypoint 前進
- 每 `0.05 s` 檢查一次車體是否進入 obstacle 或 unknown

在 20260818 地圖執行一條已驗證的短路徑：

```bash
python3 Integrated_version/planner/simulate_vehicle_path.py \\
   --map-dir outputs/maps/20260818_navigation \\
   --start-x 0.225 \\
   --start-y 1.775 \\
   --goal-x -0.075 \\
   --goal-y 1.975 \\
   --use-obstacle-distance \\
   --max-speed-mps 0.10
```

輸出：

```text
outputs/maps/20260818_navigation/simulated_vehicle_path.json
```

實測結果為 `goal_reached`，共 54 個模擬姿態點、2.65 秒。這是路徑與碰撞驗證，不會連接 ESP32，也不會輸出馬達命令。

在 3D 網頁展示路線：

```bash
python3 Integrated_version/map/export_height_color_viewer.py \\
   --ply outputs/maps/20260818_calibrated_y/20260818_floor_calibrated.ply \\
   --output outputs/maps/20260818_navigation/20260818_navigation_viewer.html \\
   --up-axis=-y \\
   --floor-height 0 \\
   --path-json outputs/maps/20260818_navigation/simulated_vehicle_path.json
```

瀏覽器開啟：

```text
http://127.0.0.1:18089/20260818_navigation/20260818_navigation_viewer.html
```

3D viewer 中紅色線是車輛模擬路線，綠色球是起點，紅色球是終點。

## 網頁導航與姿態安全條件

啟動網頁介面：

```bash
python3 Integrated_version/web/server.py \
   --map-dir outputs/maps/20260818_navigation \
   --use-obstacle-distance
```

`/api/plan` 與 `/api/navigation/start` 只接受 `current_pose.json` 中有效、`status=ok`、信心值至少 `0.5` 且 10 秒內更新的姿態。可用 `--min-pose-confidence` 與 `--max-pose-age-s` 調整門檻。`Start` 目前只更新導航狀態，尚不會送出 ESP32 馬達命令。

規劃器會拒絕地圖外座標與斜切障礙角落；啟用距離場時，路徑簡化也會保留 A* 選擇的安全成本。

回歸測試：

```bash
python3 -m unittest discover -s Integrated_version/tests -v
```
