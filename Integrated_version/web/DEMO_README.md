# Integrated Demo

這個 Demo 將既有地圖、ORB + PnP 定位、A* 規劃和差速車模擬整合到同一個網頁。

## 啟動

從 repository root 執行：

    conda run -n lingbot-map python Integrated_version/web/demo_server.py

瀏覽器開啟：

    3D 點雲檢視：同一網址後加 /3d-viewer

    http://127.0.0.1:18110

若 18110 已被使用，可以指定其他 port：

    conda run -n lingbot-map python Integrated_version/web/demo_server.py --port 18111

使用 rebuilt_colored_map.ply 的模擬導航版本：

    conda run -n lingbot-map python Integrated_version/web/demo_server.py --port 18115 --map-dir outputs/maps/20260818_navigation_rebuilt_voxel --snap-localization-to-free

重新產生 rebuilt voxel 2D map：

    conda run -n lingbot-map python Integrated_version/map/build_rebuilt_navigation_map.py --ply outputs/scenes/scene_20260818/mapping/rebuilt_colored_map.ply --output-dir outputs/maps/20260818_navigation_rebuilt_voxel --vertical-axis=-y --resolution-m 0.05 --voxel-size-m 0.04 --voxel-min-points 2 --floor-band-m 0.10 --floor-min-points-per-cell 2 --obstacle-min-height-m 0.18 --obstacle-min-points-per-cell 4 --min-obstacle-component-cells 4 --robot-radius-m 0.08

## TSDF 即時建模

第一次使用 TSDF mesh 請確認 Open3D 已安裝：

    conda run -n lingbot-map python -m pip install open3d

啟動整合前端：

    conda run -n lingbot-map python Integrated_version/web/demo_server.py --port 18115 --map-dir outputs/maps/20260818_navigation_rebuilt_voxel --snap-localization-to-free

前端流程：

1. 輸入手機 RTSP 或 HTTP 串流 URL
2. 按「連線手機」
3. 按「開始掃描建模」
4. 開啟「即時 TSDF Mesh」查看三角網格
5. 必要時開啟「即時點雲」查看原始 RGB 點雲備援

即時輸出位置在暫存 session 內：

    live/current/mapping/latest/tsdf_mesh.ply
    live/current/live_mesh.json
    live/current/live_scene.json
    live/current/mesh_navigation/latest/map.pgm
    live/current/mesh_navigation/latest/map.json

目前導航圖會從 TSDF mesh 的平坦面片重新建立，輸出仍維持既有 A-star 可讀的 map.pgm / map.json 格式。

## Demo 操作順序

1. 按「載入地圖」
2. 選擇 query 影像
3. 按「執行視覺定位」
4. 點擊地圖上的目標位置
5. 按「規劃路徑」
6. 按「開始模擬導航」
7. 用「停止」中止模擬

2D 地圖資料來源：

    outputs/maps/20260818_clean/20260818_clean.ply
    -> outputs/maps/20260818_calibrated_y/20260818_floor_calibrated.ply
    -> outputs/maps/20260818_navigation_3d/

目前 query 使用：

    outputs/scenes/scene_20260818/inputs/query_images/

這些影像是連到 data/frames/20260818_frames/ 的 symlink。

## 使用的舊程式

- experiments/orb_keyframe_localizer.py: ORB + PnP
- planner/grid_navigation.py: A* 與障礙物距離成本
- localization/localizer_interface.py: 統一 pose schema
- outputs/maps/20260818_navigation_3d/: 由清理後 3D 點雲產生的 2D 可通行性地圖
- car/car/pc_controller.py: 未來 ESP32 TCP client 的參考

## 重要限制

目前「載入地圖」使用已經建立好的 scene_20260818 與 navigation map，不會在按鈕後重新執行 LingBot-MAP 建模。這是為了先驗證定位、規劃與車體流程。

目前 Demo 使用：

    LingBot reconstruction X/Z
    -> navigation map X/Y
    -> x offset = -1.53 m
    -> y offset = 0.0 m

這個 offset 只適用目前的 20260818 Demo，未來必須由地圖校正或 Ground Truth 實驗取得，不能直接套用到其他場景。

定位結果會寫入：

    outputs/scenes/scene_20260818/results/demo/
    outputs/maps/20260818_navigation_3d/current_pose.json

模擬導航只會更新 pose 與 navigation state，不會送出 ESP32 馬達命令。
