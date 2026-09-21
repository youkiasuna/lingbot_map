# Project Result Audit

稽核日期：2026-09-17。基準 commit：`7bba832`。

範圍：目前工作目錄內的原始碼、原始影像、outputs、JSON、四份 NPZ、PLY header、PGM、distance binary、log 與相關設定。包含被 Git 忽略的本機資料，不代表只 clone repository 就能取得這些證據。README、TODO、設計文件不作為成果完成的證據。

操作限制：只讀取與唯讀計算；沒有重新執行模型推論、定位實驗、寫檔式 replay 或硬體控制，也沒有啟動 Demo。唯一新增檔案為本報告。歷史耗時是從保存的逐張紀錄重新統計，不是本次重新量測。

判定：VERIFIED = 原始碼與實際產物互相支持；PARTIALLY VERIFIED = 部分證據存在，但不能支持完整敘述；NOT VERIFIED = 證據不足；INCORRECT / OVERSTATED = 與證據不符或超出可支持範圍。

# 1. Executive Summary

目前可確認的核心成果是：**已執行的 LingBot-MAP 重建、ORB + PnP/RANSAC 的 2D–3D 定位 baseline、離線導航地圖與 A* 路徑，以及預存 prediction 的逐幀融合原型。**

- 20260818 sequence 實際有 2,127 張 JPG；mapping/query 各 43 張，兩者是同一序列的交錯取樣。
- 43 份 ORB 原始結果支持 **41 accepted、2 rejected，acceptance rate 95.348837%**；保存的單次定位 latency median 是 **211.679 ms**。
- 43-frame NPZ、1,446,504 vertices 的重建 PLY、分類點雲、occupancy grid、distance field、成功 A* path 均存在。
- Colored PLY virtual-view 定位有一個通過內部門檻的案例，記錄 **40.332162 秒**，只能稱 proof of concept，不能稱完整 benchmark 或真值確認的正確定位。
- 有 unicycle 運動學路徑模擬產物；Web Demo 另有沿 waypoint 插值的展示，兩者不能混為實車驗證。
- IP Webcam 最近 manifest 有 407 筆擷取紀錄；log 支持 30/60-frame 兩次完整更新。最新 NPZ 是 90 幀，但最新融合僅 60 幀；此融合地圖的 free cells 為 **0**。

**Ground Truth NOT AVAILABLE。** 沒有足以支持外部量測 position/yaw accuracy、RMSE、真實定位成功率、獨立重訪效能或實車自主閉迴路的資料。

本報告的重要修正：95.35% 不是定位準確率；212 ms 不是完整系統延遲；-Y-up 是目前展示/後處理的座標選擇，不是已證實的模型重力對齊保證；手機串接是累積批次重建，不是已驗證的持續每幀 online inference。

# 2. Evidence Table

以下路徑相對 repository root。為縮短表格，定義：

- `E` = `Integrated_version/experiments/`
- `M` = `Integrated_version/map/`
- `P` = `Integrated_version/planner/`
- `S` = `outputs/scenes/scene_20260818/`
- `V` = `outputs/maps/20260818_navigation_rebuilt_voxel/`
- `N` = `outputs/maps/20260818_navigation/`
- `I` = `outputs/live_sessions/ipwebcam_live/`

| Claim | Status | Code Evidence | Output/Data Evidence | Verified Value | Notes |
|---|---|---|---|---|---|
| 1. LingBot-MAP integration 已執行並產生重建 | VERIFIED | `E/run_lingbot_mapping.py`: `run`, `write_prediction_archive`; `lingbot-map-main/demo.py`: `postprocess`, `_get_world_points` | `S/mapping/predictions.npz`, `run.json`, `preprocessed/*.png`, `rebuilt_colored_map.ply` | 43 frames；PLY 1,446,504 vertices | 不代表重建幾何精度已驗證；舊 `videos/...` 路徑已失效，實體資料在 `data/frames/` |
| 1a. -Y-up 是模型保證的世界重力方向 | INCORRECT / OVERSTATED | `E/run_research_pipeline.py` 預設 `--viewer-up-axis=-y`; `M/build_rebuilt_navigation_map.py`: `axis_indices`; viewer `camera.up.set(0,-1,0)` | `V/map.json`: `vertical_axis=-y`, `horizontal_axes=XZ` | 可確認目前後處理/展示採 -Y-up | archive 沒有施加重力校正；不能推論任何輸入都天然 -Y-up |
| 2. ORB + Hamming + 2D–3D PnP/RANSAC baseline | VERIFIED | `E/orb_keyframe_localizer.py`: `OrbKeyframeLocalizer`, `lookup_2d_3d_correspondences`, `pose_from_pnp` | `S/results/orb/000000_result.json` 等 43 份 | pose、inlier、reprojection、confidence 均有輸出 | 成功執行不等於外部真值正確 |
| 3. 41/43、95.35% acceptance | VERIFIED | `E/analyze_external_queries.py`: `status_for_result`; localizer `result_to_pose` | 43 份 `S/results/orb/*_result.json` | 41 / 43 × 100 = 95.3488372093% | 與 summary 相符；稱「定位準確率」則為 OVERSTATED |
| 4. ORB median 約 212 ms | VERIFIED | `OrbKeyframeLocalizer.localize` 中的 `perf_counter` 區段 | 同上，43 個 `latency_ms` | median 211.679 ms | 排除 reference 初始化、建圖、viewer、輸出寫檔；不是端到端 benchmark |
| 5. Colored PLY virtual-view 定位已有成功案例 | VERIFIED，限 proof of concept | `E/colored_pointcloud_localizer.py`: `read_ply_sample`, `render_view`, `localize`; 共用 `pose_from_pnp` | `S/results/colored/000000_result.json` | localized；44 matches；31 inliers；40,332.162 ms | 只有一個通過案例；另有一個外部 query 失敗結果；不能視為完整 benchmark |
| 6. Three.js 同時顯示 RGB 點雲、mapping cameras、localized query camera | PARTIALLY VERIFIED | `colored_pointcloud_localizer.py`: `build_colored_viewer_html`; `E/localize_query_in_3d_viewer.py`: `build_viewer_html` | 重建 PLY、NPZ、pose JSON 存在；`S/visualization/auto_floor_viewer.html` 是實際點雲 viewer | 功能碼存在；目前未保留對應 per-query HTML | 一般 ORB viewer 是固定青色點，不是 PLY 原始 RGB；沒有本次瀏覽器/截圖驗證 |
| 7. 點雲分類、occupancy、inflation、distance field | VERIFIED | `M/build_rebuilt_navigation_map.py`; `M/build_3d_navigation_map.py`; `M/build_obstacle_distance.py` | `V/floor.ply`, `obstacle.ply`, `unknown.ply`, `map.pgm`, `navigation_map.json`, `obstacle_distance.bin` | 77×55；free 1,271；occupied 975；unknown 1,989；distance 4,235 float32 | 參數使用 `_m` 命名，但現實公尺尺度未校正 |
| 8. A* 2D path planning 有成功產物 | VERIFIED | `P/grid_navigation.py`: `astar_pixels`, `neighbors`, `plan_path` | `N/planned_path.json`; `outputs/maps/20260818_navigation_rebuilt/planned_path.json` | 分別 7 nodes / 0.3828427、6 nodes / 0.25 地圖單位 | 舊地圖與 rebuilt 地圖均有產物；V 本身未保存 planned_path，不能移植別張地圖的成功紀錄 |
| 9. Vehicle/path simulation prototype | VERIFIED，限簡化模型 | `P/simulate_vehicle_path.py`: `simulate`; `Integrated_version/web/demo_server.py`: `simulate` | `N/simulated_vehicle_path.json` | 54 poses；2.65 秒模擬時間；goal_reached | 離線腳本是 unicycle 運動學；Web 是 waypoint 插值；均非實車 |
| 10. 預存 prediction incremental replay/fusion | VERIFIED | `E/run_lingbot_online_replay.py`: `main`; `M/incremental_voxel_map.py`: `IncrementalVoxelMap.update` | `S/online_replay/online_replay_summary.json` 的 43 timeline entries、9 snapshot dirs、最終 PGM/PLY | 43 frames；最終 74×50，888 free | 類型 B：incremental replay/fusion of precomputed predictions；不是新增 RGB 時呼叫模型 |
| 11. 手機擷取與兩次批次更新 | VERIFIED，限紀錄支持的範圍 | `E/capture_phone_stream.py`; `E/run_live_mapping_pipeline.py`: `capture_loop`, `process_once` | `I/capture_manifest.json`, `pipeline.log`, `pipeline_status.json`, NPZ、replay timeline | 407 manifest entries；2 次完整更新；60-frame replay；90-frame 最新 NPZ | 資料夾有 2,092 JPG，混有 manifest 未列出的 1,685 張；不是單次乾淨 session |
| 11a. 已完成手機每幀即時推論與可導航更新 | INCORRECT / OVERSTATED | `process_once` 每次以 `--first-k N` 啟動新的 mapping 子程序 | log 的 30 → 60 → 90；最終 replay PGM | 最終 6×10，49 occupied、11 unknown、0 free | 模型內部 streaming API 不等於手機系統持續 online inference；無可導航 free cells |
| 12. 外部 Ground Truth / accuracy / RMSE | NOT VERIFIED | 僅 example config 引用不存在的 `queries/ground_truth.jsonl`；上游誤差工具函式不構成真值資料 | 未找到配對實測 pose、tag、mocap、LiDAR 或手工量測標籤 | Ground Truth NOT AVAILABLE | 不能報 position/yaw accuracy、RMSE 或 true localization success rate |
| 13. SuperPoint / LightGlue 已比較或完成 benchmark | NOT VERIFIED | 未找到專案實作/呼叫；指定 `lingbot-map` 環境套件 metadata 與 module lookup 均無命中 | 未找到相關 benchmark result | 無可核實的安裝/執行/比較成果 | 未掃描所有其他 conda 環境，不能推論整台電腦從未安裝 |
| 14. ESP32 完整自主閉迴路 | NOT VERIFIED；宣称完成則 OVERSTATED | `car/car/{pc_controller.py,web_controller.py,esp32_motor_control.ino}` 是手動 TCP 控制；Demo 未串接馬達 | 未找到 localization→planning→motor→feedback 的一次完整執行紀錄 | firmware 接受 F/B/L/R/S；設定 motor_output_enabled=false | 車輪尺寸與相機外參未設定；ACK 不是運動回授；無實車自主導航證據 |

## 2.1 ORB Pipeline 的精確實作

來源：[orb_keyframe_localizer.py](Integrated_version/experiments/orb_keyframe_localizer.py)、[analyze_external_queries.py](Integrated_version/experiments/analyze_external_queries.py)。

1. 初始化：從 `mapping/predictions.npz` 取得 `world_points` 與 `intrinsic`；從 `mapping/preprocessed/<index>.png` 建立 reference ORB features。`analyze_external_queries.py` 預設 `frame_stride=1`；43 份結果皆記錄 `reference_count=43`。注意 localizer class 自己的預設 stride 是 5，Web Demo 不一定使用此 43-reference 設定。
2. Query：`cv2.imread`，直接 resize 到 world_points 的寬高，本場景是 518×294；BGR→gray；`cv2.ORB_create(nfeatures=2000).detectAndCompute`。
3. Matching：對 reference descriptors 使用 `BFMatcher(NORM_HAMMING, crossCheck=False)`；`knnMatch(k=2)`；保留 `best.distance < 0.75 * second.distance`。沒有 mutual matching/cross-check。
4. Reference search：依 good-match 數量排序；只對 top 5 references 做幾何候選。這些是目前執行入口預設，歷史 JSON 未完整保存所有 CLI 參數，不能把所有預設當作歷史命令行已獨立留證。
5. 2D–3D：把 matched reference keypoint 四捨五入為像素 `(x,y)`，取 `world_points[reference.index,y,x]`；搭配 matched query 的 2D pixel。按 descriptor distance 最多取前 300 matches，排除越界、非有限點、norm < 1e-6。此 ORB correspondence 步驟**沒有另用 depth_conf 過濾**。
6. PnP：good matches 至少 25 才嘗試；有效 3D points 至少 4。呼叫 `cv2.solvePnPRansac(..., flags=SOLVEPNP_ITERATIVE, iterationsCount=200, reprojectionError=5.0, confidence=0.99)`；distortion 傳 `None`。PnP 回傳至少 4 inliers 才視為有幾何解；達 12 inliers 標記候選 `pnp_status=ok`。
7. Intrinsic：使用 **該 reference 的模型預測 `intrinsic[reference.index]`**，不是獨立校正的 query K。Query 直接 resize，mapping 由 PIL bicubic、patch-size 對齊及必要 center crop 前處理。1920×1080 同序列影像此次均到 518×294，但外部不同相機/長寬比不能據此認為內參正確。
8. Confidence：`0.25*min(matches/80,1) + 0.55*min(inliers/(2*min_inliers),1) + 0.20*clip(1-mean_reprojection/10,0,1)`，四捨五入 4 位。它是 heuristic score，不是經校準的成功機率。
9. 選 best：按 `(confidence,inlier_count,match_count)` 排序比較。best 的 PnP status=ok 才給 raw result `localized`；分析/pose publication 另要求 confidence ≥ 0.35。沒有外部 position/yaw error gate，也沒有獨立 mean-reprojection hard gate；5px 是 RANSAC 的 inlier 判斷參數。
10. Pose：PnP 得到 world-to-camera `R,t`；camera center = `-R.T @ t`。forward = `R.T @ [0,0,1]`；yaw = `degrees(atan2(forward.x,forward.z)) % 360`。保存 `position_xyz` 與 yaw；`result_to_pose` 用 X/Z 當 demo 平面 X/Y，沒有外部尺度校正。

## 2.2 座標、Colored PLY 與 Viewer

- `run_lingbot_mapping.py` 使用模型預測及上游 postprocess；`demo.postprocess` 將 pose encoding 解碼後的 w2c 反矩陣變成 c2w。`_get_world_points` 使用既有 world_points，或以 depth、K、c2w 反投影。archive 寫入沒有套用地板校正矩陣或重力旋轉。
- 因此「LingBot reconstruction coordinates」成立；「模型保證 -Y 為真實鉛直」不成立。`calibrate_floor_plane.py` 是另外的後處理，不能與 raw reconstruction 的座標混用。不同 outputs 也保留 y/z 等校正版本，不能聲稱所有檔案使用同一座標系。
- Colored 方法讀取 binary colored PLY，stride sampling 後保留 144,651 點；virtual camera 使用 mapping archive 的每個 `extrinsic_c2w` 與 K，不是任意新視角搜尋網格。
- `render_view` 以 `(points-center) @ rotation` 變換、投影到像素；剔除 depth≤0.05 與影像外點；按深度排序，以預設半徑 2 的 splat 填 RGB 與 point-id buffer。Rendered RGB 是由 PLY RGB 產生，之後共用 ORB extractor；其 extractor 用 BGR2GRAY，並未特別為 rendered RGB 轉換通道，這是目前實作細節，不應隱去。
- Matched rendered pixel 的 point-id 直接映射到 PLY XYZ，再共用 RANSAC PnP。不是用 query depth 建 3D。
- RGB + reference/query markers 的 Three.js 程式在 `colored_pointcloud_localizer.py`；一般 `localize_query_in_3d_viewer.py` 的 cloud 固定青色，marker 是球形位置標記，不是已驗證完整 query 6DoF frustum。
- 掃描現存 18 份 generated HTML，沒有保留這兩個定位 generator 對應的 `query_camera` / `references` payload；ORB summary 的 viewer_html 為 null。`S/visualization/auto_floor_viewer.html` 可支持點雲展示產物存在，不能代替 query localization overlay 的保存證據。沒有重新開瀏覽器驗證 CDN/WebGL 當下可用性。

## 2.3 Navigation Map、A* 與 Simulation

**Rebuilt voxel 版本（V）：**

- Source 是 `S/mapping/rebuilt_colored_map.ply`，不是直接使用 6GB dense PLY。
- 高度 `h=-Y`；先由高度低百分位區間 histogram peak 估計 floor height。metadata 記錄 floor height=0.059083275496959686；voxel size=0.04，voxel 至少 2 點。
- floor：`abs(h-floor_height) ≤ 0.10`；obstacle：相對高度介於 0.18 與 2.0；其他保留點屬 unknown point cloud。Grid unknown 另指沒有足夠 floor 證據、也沒有被 obstacle 覆蓋的格子，不等同 unknown 點的投影數。
- Grid resolution=0.05；每格 floor 至少 2 點、obstacle 至少 4 點；去除少於 4 格的 obstacle components。Robot radius=0.08，`ceil(0.08/0.05)=2` 格圓形膨脹，格網離散半徑相當於 0.10 地圖單位，不是精確 0.08 的連續圓。
- PLY header 重算：floor 1,167,448、obstacle 163,254、unknown 115,284，共 1,445,986，與分類 metadata 相符。
- PGM 重算：77×55=4,235 格；0=occupied 975、205=unknown 1,989、254=free 1,271。
- Distance field：從 occupied cells 起始，多源 Dijkstra，8 鄰接步長為 resolution 或 sqrt(2)*resolution。這是格網 octile 距離近似，**不是精確連續 Euclidean distance transform**。只把 occupied 當來源，不把 unknown 當障礙來源。
- 本次在記憶體重新計算 V 的 4,235 個 float32 與 N 的 17,152 個 float32，皆與 `obstacle_distance.bin` 完全一致。
- 實際產物為 PLY、PGM、JSON、BIN；不要在這條 pipeline 宣稱有不存在的 NPY。解析格式及計算皆不寫回。

**A*：**

- State 是 `(pixel_x,pixel_y)`。8-connected，直行成本 1、斜行 sqrt(2)，禁止對角穿越兩側 blocked corner。
- Heuristic 是 octile distance。可選 distance-field soft penalty：距離小於 safety radius 時加 `risk_weight * ((radius-distance)/radius)^2`。
- `is_traversable` 以輸入 grid 判斷；已膨脹的 occupied 格不可穿越，unknown 預設不可走。A* 不會自己重新做 inflation。
- 既存 `raw_path` 已逐段檢查：4 份 planned_path 都是可通行格與合法相鄰步驟；重算長度符合 JSON 的四捨五入結果。這不是重新跑 A* 寫出一條替代路徑。
- `20260818_navigation_rebuilt` 的 `use_obstacle_distance=true` 並不證明當次真的有 distance penalty：目前該目錄沒有 distance binary，`load_obstacle_distance` 缺檔時回傳 None，planner 仍可把請求 flag 保存為 true。因此 rebuilt path 可以支持 A*，不能單憑 flag 宣稱 distance-aware 規劃已驗證。
- V 有距離場但沒有保存 path；N 同時有距離場與 path。不要把不同地圖的證據當作同一場完整實驗。

**Simulation：**

- `simulate_vehicle_path.py` 是離散時間 unicycle kinematics：`yaw += angular*dt`，`x += linear*cos(yaw)*dt`，`y += linear*sin(yaw)*dt`。角速度由 heading error 控制且限幅；偏航較大先轉向；有 footprint/grid collision check。
- 沒有輪半徑/輪距到左右輪轉速的動力學、摩擦、打滑、馬達響應或感測器噪聲。因此可稱「簡化差速車 unicycle 運動學模擬」，不可稱真實車輛動態驗證。
- 保存結果 N：start=(0.225,1.775)、goal=(-0.075,1.975)，54 個 trajectory poses，最後 time=2.65s。最後位置=(0.0045066720,1.9219955520)，不是精確等於 goal；goal_reached 是 tolerance 達標，不是零誤差。
- Web `DemoHandler.simulate` 則是 waypoint 線性插值，每約 0.04 地圖單位一段、每段 wait 0.08s，寫回模擬 pose，不呼叫 ESP32。不要用離線 unicycle 的結果替 Web 展示宣稱物理模型。

# 3. Numerical Verification

## 3.1 Mapping、Query 與 NPZ

| 檢查 | 重新計算結果 |
|---|---|
| `data/frames/20260818_frames/*.jpg` | 2,127，000000 至 002126 |
| Mapping links | 43，來源 000000、000050、…、002100 |
| Query links | 43，來源 000025、000075、…、002125 |
| Manifest 86 筆來源與實際 link targets | 全部一致且存在 |
| Mapping/query 來源 path 交集 | 無 |
| Mapping/query JPG SHA-256 完全相同內容 | 無 |
| `data/videos/20260818.mp4` OpenCV container metadata | 2,127 frames，約 29.863 FPS |
| 重建 PLY | 1,446,504 vertices；binary_little_endian；XYZ float32、RGB uint8、confidence float32 |

Split 檔名會重新編號：query `000000.jpg` 實際是 source `000025.jpg`；query `000042.jpg` 實際是 source `002125.jpg`。不要把 split index 當成原影片 frame index。

同一 extracted sequence 的來源可由 link/manifest 直接確認；影片檔與抽幀目錄名稱及 frame count 一致，但沒有保存完整原始抽幀命令/逐幀 hash provenance，因此不把影片每一解碼幀到 JPG 的 byte-level 對應也宣稱已验证。

`S/mapping/predictions.npz` 實際 keys，全部以 `allow_pickle=False` 讀取：

| Key | Shape | dtype |
|---|---|---|
| schema_version | () | int32 |
| frame_paths | (43,) | `<U67` |
| extrinsic_c2w | (43,3,4) | float32 |
| intrinsic | (43,3,3) | float32 |
| world_points | (43,294,518,3) | float64 |
| depth | (43,294,518,1) | float32 |
| depth_conf | (43,294,518) | float32 |

沒有 `world_points_conf` key。實際舊產物為 schema 1/absolute frame paths；目前 writer 已寫成 schema 2/relative paths，不能將「目前程式預設格式」套用到舊檔。

**Metadata 不一致：**四份 NPZ 的 companion predictions.json 都留下舊的 frame_paths string dtype 寬度；其他陣列 shape/dtype 對照無差異。

| NPZ 所在目錄 | JSON frame_paths dtype | 實際 NPZ dtype | 實際 frames |
|---|---|---|---:|
| `S/mapping` | `<U62` | `<U67` | 43 |
| `I/mapping/latest` | `<U105` | `<U82` | 90 |
| `outputs/live_sessions/iphone_live/mapping/latest` | `<U103` | `<U80` | 30 |
| `outputs/live_sessions/iphone_test/mapping` | `<U103` | `<U80` | 30 |

這是保存描述未同步，不代表幾何陣列已損毀；本報告以實際 NPZ 為準，未改檔修正。

## 3.2 ORB Acceptance 與 Latency

來源：`S/results/orb/000000_result.json` 至 `000042_result.json`，沒有只採用 summary 總數。

重算規則：`status == localized`，best pose 存在、PnP ok，且 confidence≥0.35。43 份 raw 結果與 summary records 的 status、query、frame index、matches、inliers、reprojection、confidence、XYZ、yaw、latency 均一致。

| 統計 | 重算值 |
|---|---:|
| Total | 43 |
| Accepted | 41 |
| Rejected | 2 |
| Acceptance rate | 95.34883720930233% |
| Latency count | 43 |
| Mean | 200.2112325581 ms |
| Median | 211.679 ms |
| Min | 31.762 ms |
| Max | 260.884 ms |
| P90 | 241.589 ms |

P90 使用 NumPy percentile 的 linear interpolation；包括 accepted 與 rejected，不是只挑成功樣本。summary localized_rate=0.9535 是四捨五入後的一致值。

兩筆 rejected：split 000007/source 000375，confidence=0.1781、inliers=0；split 000037/source 001875，confidence=0.0594、inliers=0。

逐張 latency 原始數值（ms，依 split index）：

```text
000000 260.884   000001 237.118   000002 228.532   000003 226.626
000004 242.119   000005  67.538   000006 228.764   000007 164.092
000008 238.516   000009 259.191   000010 251.571   000011 244.454
000012 239.469   000013 204.822   000014 204.082   000015 202.965
000016 211.679   000017 206.476   000018  67.721   000019 230.558
000020 232.868   000021 226.733   000022 221.333   000023 195.132
000024 206.007   000025 205.095   000026 197.461   000027 153.784
000028 221.101   000029  65.901   000030 214.726   000031 217.968
000032 195.642   000033 178.081   000034 217.324   000035 193.239
000036 204.770   000037  31.762   000038 218.186   000039 180.039
000040 217.778   000041 197.793   000042 199.183
```

**計時邊界：**`localize()` 進入即開始，包含 query image disk read/decode、resize、gray/ORB extraction、對 references matching/search/ranking、top-k 2D–3D lookup、RANSAC PnP、pose/reprojection/confidence/candidate selection。截止於整理最終 result payload 之前。**不含** constructor 的 NPZ 載入、reference images loading/features、模型建圖、網路擷取、viewer rendering、JSON/pose 寫入。因此 disk I/O 是「包含 query 讀取，不含後續寫檔」，不能一概說排除全部 I/O。

目前結果未保存足以重建完整歷史硬體負載、套件版本、warm-up/repeat 設定的 run manifest；212ms 是此份已保存 run 的統計，不能外推為所有場景或硬體的保證。

## 3.3 Virtual-view Latency

`S/results/colored/000000_result.json`：latency=40,332.162ms=40.332162s，status=localized，31 inliers，mean inlier reprojection=2.5501px，confidence=0.8365。只有一筆成功案例，不報有統計意義的均值/分位數。

計時起點在 query 讀取、resize、query ORB 之後；包含遍歷 mapping cameras 的 virtual-view rendering、reference ORB、matching、2D–3D lookup、PnP、candidate selection。排除 PLY/NPZ 載入、PLY sampling、query preprocessing/features、HTML/JSON 寫入。與 ORB 212ms 的計時邊界不同，不能直接當作公平 speedup benchmark。

另有 `S/external_query_results/IMG_1280_colored_result.json`：162.967ms、0 matches、0 inliers、low_confidence，point_count=99,992、stride=3,239。設定/輸入點雲取樣不同且失敗，不能與上述成功案例混算成同條件 benchmark；該 JSON 沒有完整 PLY 路徑與 run 參數，亦不應補猜它使用哪份 PLY。

## 3.4 IP Webcam 與 Replay

| 指標 | 重新查核 | 判讀 |
|---|---|---|
| 最近 manifest 的 frames list | 407 entries，407 個對應 JPG 均存在 | 與 saved_frames=407、status frames_captured=407 一致 |
| 實際 `I/frames/*.jpg` | 2,092 張，index 0..2091 | 比 manifest 多 1,685 張，不可說「該資料夾只有407張」 |
| Capture read_frames | manifest 記錄 2,437 | 沒保存所有未取樣讀取幀，無法獨立重算：NOT VERIFIED 的原始總讀取量 |
| 最近完整更新 | 30-frame mapping→replay→viewer；60-frame mapping→replay→viewer | log 重算 2 組完整鏈，與 updates_completed=2 一致 |
| 第三輪 | 90-frame NPZ 與 PLY 已產生；沒有後續 90-frame replay 完成鏈 | 不能把 frames_processed=90 當作完整融合90幀 |
| 最新 replay | 60 個唯一 frame-index timeline entries，12 個 frame_000005..000060 snapshots | 與 frames_integrated=60 一致 |
| 最新手機 replay grid | 6×10；occupied=49、unknown=11、free=0 | 更新產物存在，但不是可通行導航地圖 |
| 固定 scene replay | 43 個唯一 timeline entries；9 個 snapshots；74×50 PGM | free=888、occupied=870、unknown=1,942 |

Log anchors（`I/pipeline.log`，時間為檔案原文，不混用系統當下時區）：

- 15:02:21 開始 first-k 30；15:02:52 incremental map 30；15:02:53 寫完 viewer，Frames: 6（這是 snapshots 數，不是 capture frames）。
- 15:02:53 開始 first-k 60；15:03:37 incremental map 60；15:03:39 寫完 viewer，Frames: 12。
- 15:03:39 開始 first-k 90；15:03:43 stream read failed。尾段仍記錄 90-frame NPZ/PLY 寫入完成，但沒有 90-frame replay/viewer 完成紀錄。
- 此 log 也包含更早的多次執行與 `No points passed the PLY export filters` 錯誤；不能把整份 append log 當成一次乾淨成功 run，也不能把所有 mapping 行都當成功更新。

手機流程判定為 **C：累積影像後分批 reconstruction/update**，每次啟新程序載入模型，對 first-k 30、60、90 重新推論，再進行 **B：預存 prediction replay/fusion**。上游模型本身確有 inference_streaming，但這不足以把整個手機流程稱為 A：持續每新幀 real-time incremental inference。

`S/online_replay` 的 elapsed_sec=0.69、手機 replay 的 0.28 只保存在 summary，沒有原始 start/end timer 資料可独立重算，作為耗時實驗數字標記 **NOT VERIFIED**，本報告不把它們列為可報效能。程式可確認該 timer 排除模型 inference、NPZ 載入與 bootstrap，包含逐幀融合及週期檔案輸出。同理 `S/mapping/run.json` 的 inference_seconds=6.648 僅是保存的自報值，本次未獨立驗證其耗時。

## 3.5 其他數值與 Metadata 注意事項

- 外部 ORB 三份 raw result 重算：IMG_1279 localized/confidence 0.4961；IMG_1280 low_confidence/0.5043；IMG_1281 low_confidence/0.429。只有 **1/3 通過 raw status + 0.35 gate**。這三張另放的照片沒有完整量測/拍攝 provenance，不能直接升格為正式 independent revisit benchmark。
- N 的 map.json `counts.free_cells=5242`，但實際 PGM free=62、occupied=7271、unknown=9819。程式顯示 free_cells 是 obstacle 覆蓋前的 floor-supported mask count，不是最終可走格數。這是欄位語義陷阱，不能拿 5242 當最終導航空間。
- 四份保存的 A* raw paths 重算長度：`20260804_map_vis`=1.4、`20260818_navigation`=0.3828427125、`20260818_navigation_3d`=0.3828427125、`20260818_navigation_rebuilt`=0.25。都是地圖座標的幾何長度，不是外部量測公尺精度。
- `20260818_navigation_rebuilt` 的成功例：start=(0.125,1.175)，goal=(0.075,0.975)，6 raw nodes、3 waypoints。N 的成功例：start 請求=(0.2261,1.7799)，goal=(-0.075,1.975)，7 raw nodes、3 waypoints。Planner 會把位置對應到 grid cell center，與請求值有離散化差異。

# 4. Pipeline Verification

| 階段 / 連接 | 判定 | 程式與實際產物 |
|---|---|---|
| Monocular RGB → LingBot-MAP | VERIFIED | `run_lingbot_mapping.run`；source JPG、43 mapping links、mapping/run.json |
| LingBot-MAP → 3D reconstruction | VERIFIED | postprocess + archive/PLY exporter；S 的 predictions.npz、preprocessed PNG、rebuilt PLY |
| Query RGB + map → ORB 2D–3D correspondences | VERIFIED | `OrbKeyframeLocalizer`；43 query results 的 matches/candidates |
| Correspondences → PnP/RANSAC → camera pose | VERIFIED | `pose_from_pnp`；best.position_xyz、yaw、inliers、reprojection |
| Camera pose → 外部正確位置/角度 | NOT VERIFIED | 無 Ground Truth/座標對齊量測 |
| Camera pose + RGB point cloud → Three.js overlay | PARTIAL | 生成碼與輸入/pose 資料存在，但沒有保存對應定位 HTML/截圖；一般點雲 HTML 存在 |
| 3D point cloud → navigation map | VERIFIED | rebuilt/classification 程式；V 與其他 map 的 PLY、PGM、JSON、distance binary |
| Navigation map → A* | VERIFIED | `grid_navigation.py`；N / rebuilt 等已保存且合法的 paths；不是每一張地圖均有證據 |
| ORB pose → navigation-map start（完整校正） | PARTIAL | Demo 有 X/Z 平面映射、預設 x offset=-1.53、可選 snap-to-free；沒有外部校正證據，不能當定位準確度或一致的物理 frame |
| A* → vehicle simulation | VERIFIED，限離線簡化模擬 | `simulate_vehicle_path.py` 與 N/simulated_vehicle_path.json；Web 另有插值實作 |
| Localization → planning → ESP32 → motor → feedback | NOT VERIFIED | 手動控制碼存在，無完整閉迴路執行/感測回授紀錄 |

原本把所有步驟畫成單一路徑容易誤導：**navigation map 是由 3D point cloud 建立，不是由 Three.js viewer 產生。** 可以呈現離線研究模組鏈，但不能寫成「已量測驗證、同一場景同一次執行、全自動實車閉迴路」。

# 5. Evaluation Limitations

1. **Ground Truth NOT AVAILABLE。** 設計文件中的真值路徑與上游 error 函式都不是實驗標籤；current_pose、simulated trajectory、LingBot 自己輸出的 camera poses 也不是外部真值。
2. **In-sequence，不是 independent revisit。** Mapping IDs=50k，query IDs=25+50k，來源同一 extracted sequence；每張 query 距離最近 mapping frame 25 個來源 frame。若按現存原片約29.863 FPS、一對一抽幀解讀，约0.84秒；這個秒數依賴抽幀 provenance 假設，不作已獨立驗證的時間間隔數字。
3. **資料洩漏與重疊風險。** 沒找到 mapping/query 相同來源檔或相同 SHA-256 的直接重複；因此不斷言 query 被直接拿去建圖。但同片相鄰時間影像可能高度重疊，測試不獨立。Overlap 百分比與移動距離沒有量測，不能補猜。調參過程是否反覆使用這43張，也缺少獨立紀錄，不能宣稱嚴格 held-out。
4. **相機校正不足。** Query 用 reference 預測 K，distortion=None；`visual_navigation/config/camera.json` calibration_status=UNSET，fx/fy/cx/cy 與 camera_to_base 為 null。未證明不同手機、焦距、裁切、長寬比的 query 正確映射到此 K。
5. **Metric scale 未驗證。** 輸出 `_m`、resolution_m、robot_radius_m 都是程式命名/設定；沒有外部長度量測、scale alignment 或 scale error 資料可證明公尺精度。不得將點雲單位直接當成可驗證的真實距離。
6. **Acceptance 不等於 accuracy。** Gate 是匹配/PnP幾何與 heuristic confidence；沒有與真值位置/角度容許誤差比較。95.35% 只能報 gate acceptance。
7. **座標介面未完整校正。** ORB yaw 是 atan2(forward.x,forward.z)，Web 插值 yaw 是 atan2(delta_y,delta_x)，加上 offset/snap 與不同 map variants，不能因格式都有 yaw_deg/x_m 就聲稱物理座標一致。Snapped pose 不可當原始定位估計計算 accuracy。
8. **效能範圍不同。** ORB 與 colored 方法的 timer 不同；沒有同條件多次 run 的 benchmark。Replay 耗時不包含模型。手機 update 是累積重跑，且 capture/NPZ/replay 不同階段可能停留在不同版本。
9. **成果來源完整性不足。** 多個程序寫 latest、session 跨次共用、log append、JSON metadata 部分過時。數字必須綁定具體檔案與階段，不應只引用 status 或 README。
10. **實車與新方法缺證據。** `vehicle.json` 輪半徑/輪距為 null，motor_output_enabled=false；ESP32 ACK 只代表命令收到。Web speed command 預設 `V{value}`，目前 firmware 只有 F/B/L/R/S 分支，亦不能把 UI 速度控制當成已驗證硬體能力。SuperPoint/LightGlue 沒有可比結果。

# 6. Professor-Safe Claims

## 目前可以安全對教授說的成果

- 「已整合 LingBot-MAP，對同一序列中選取的43張影像產生相機參數、dense 2D–3D predictions 與1,446,504點的重建 PLY。」
- 「已實作並執行 ORB/Hamming matching、reference pixel 對應 LingBot world_points、PnP/RANSAC 的視覺定位 baseline。」
- 「在43張與 mapping frames 交錯取樣的 in-sequence queries 中，41張通過目前 acceptance gate，比例95.35%；尚未評估外部真值誤差。」
- 「此份保存 run 的43筆單張定位 latency，median=211.679ms、mean=200.211ms、P90=241.589ms；不含地圖與reference初始化、網路擷取、viewer和結果寫檔。」
- 「完成 colored PLY virtual-view 定位 proof of concept，一個 query 通過內部PnP門檻，記錄的render/search/PnP區段為40.332秒；尚非完整benchmark。」
- 「完成由重建點雲產生 floor/obstacle/unknown、inflated occupancy grid 與格網距離場；存在已保存且路徑合法的A*結果。」
- 「完成簡化unicycle路徑追蹤模擬案例，保存54個pose、2.65秒模擬軌跡；沒有宣稱實車測試。」
- 「完成43幀預存prediction的incremental replay/fusion；手机已初步接上擷取與累積批次重建，最近紀錄有407張擷取、兩次完整更新、60幀融合結果，但該次手機grid沒有free cells。」
- 「Three.js點雲展示產物存在；定位相機疊圖生成程式已實作，但目前repository未保留對應HTML/截圖，尚不足以作完整展示留證。」

## 目前不能這樣宣稱的成果

- 「定位準確率95.35%」、「真實定位成功率95.35%」、「已知position RMSE/yaw accuracy」。
- 「已完成独立重訪測試」、「對新環境或新手機已證明泛化」。
- 「整套系統端到端延遲212ms」、「40.3秒是完整colored流程耗時」、「兩者已有公平效能比較」。
- 「LingBot輸出的-Y一定是重力方向」、「0.05一定是真實5cm」、「導航軌跡已證明公尺精度」。
- 「手機每個新RGB持續即時inference並維持地圖」、「407張全部完成建圖」、「90張已完成融合」、「手機地圖可直接導航」。
- 「目前有一份保存的Three.js結果已同時驗證RGB點雲及query/mapping cameras」。
- 「完成SuperPoint/LightGlue benchmark」、「完成ESP32實車自主導航與閉迴路避障」。

# 7. Corrections to Previous Project Summary

使用者提供的是14組待查 claims，而非另外一份完整原始摘要；以下逐條比對這些 claims，不補造其他原文。

| 原描述 | 應修改 | 原因 |
|---|---|---|
| 1. 輸入 videos/20260818_frames，約2127張，mapping/query各43 | 現在為 data/frames/20260818_frames，實數2127；43+43交錯split成立 | 路徑已搬移；manifest與links重算一致 |
| 1. 目前專案採用-Y-up | 本場景viewer及導航後處理採-Y-up；raw archive是LingBot reconstruction frame | 沒有模型重力保證；另存不同axis校正版本 |
| 2. ORB+PnP 2D–3D baseline 已完成 | 保留，但限baseline實作與執行；query使用reference預測K | 原始碼與43份結果支持，不支持外部pose精度 |
| 3. 41/43、95.35% | 保留數字，稱in-sequence acceptance rate；不可稱準確率 | 逐張重算成立，沒有Ground Truth |
| 4. median約212ms | 此run中localize區段median=211.679ms；不含初始化等 | timer與原始43值支持；不是端到端 |
| 5. Colored PLY定位完成、單張40.3秒 | 一個成功gate案例的proof of concept；該timer區段40.332162秒 | 一筆成功、一筆不同設定的失敗；計時邊界不同 |
| 6. Viewer已顯示RGB cloud與兩種camera | 程式具備，點雲viewer有產物；完整定位overlay僅部分驗證 | 對應query HTML未保留；一般ORB cloud是固定青色 |
| 7. Navigation map完整流程已完成 | 離線分類/inflation/distance產物成立；不代表實際可行駛精度 | V的PGM與distance重算吻合；手機版本free=0 |
| 8. A*完成 | 成功離線path成立；不等同實車自主導航 | 保存raw_path合法且長度可重算 |
| 9. 車輛模擬完成 | 離線unicycle kinematics案例與Web插值Demo分別描述 | 沒有動力學/馬達/輪速回授驗證 |
| 10. Incremental mapping | 明確寫預存prediction incremental replay/fusion | replay不呼叫LingBot；模型streaming不等於系統持續線上串流 |
| 11. IP Webcam擷取407、更新2次、融合約60 | 最近manifest407；兩次完整批次更新；保存融合恰60；最新NPZ90；資料夾2092 | 多輪殘留與不同階段latest不一致，不能混用 |
| 12. 可報position/yaw accuracy | Ground Truth NOT AVAILABLE，不能報accuracy/RMSE | 無外部量測標籤與配對評估 |
| 13. SuperPoint/LightGlue已用於成果 | NOT VERIFIED | 指定環境無套件證據；repo無實作/結果 |
| 14. ESP32實車自主導航完成 | 有手動TCP控制碼；完整自主闭迴路NOT VERIFIED | 無localization→motor→feedback完整證據 |

## 最後五個問題的直接答案

1. **41/43真的存在：是。** 43份per-query JSON重算得到41 accepted、2 rejected；95.35%是同序列gate通過率。
2. **212ms median真的存在：是。** 原始43個latency的median=211.679ms，僅限上述計時區段與保存run。
3. **完成ORB+PnP 2D–3D localization：是，baseline層級。** 有world_points對應、RANSAC PnP與實際pose輸出；真實accuracy未驗證。
4. **完成點雲→navigation map→A*：是，離線模組/產物層級。** rebuilt map有成功path；V另有分類與distance場。尚未證明所有map版本或手機輸入皆可導航，更不是實車完成。
5. **明天可交的數字：**2127 source frames、43 mapping/43 in-sequence queries、41/43 acceptance、211.679ms局部median、1,446,504 PLY vertices、已重算的grid/path數據及54-pose模擬案例。手機數字須連同407 manifest/2092磁碟檔、兩次完整更新/60融合/90NPZ、0 free cells的限制一起報告。不得放accuracy、RMSE、獨立重訪或實車自主導航的完成宣稱。
