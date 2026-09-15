# Online Mapping Research Plan

這份文件整理目前專題從離線建圖轉成線上增量建圖的研究路線。

## 核心方向

研究主題：

    基於視覺 3D 重建之即時增量地圖建立與導航可通行區推估

目前先使用 saved predictions 做 online replay，不直接接相機。這可以先驗證 runtime map 設計，再把資料來源換成真正的 LingBot-MAP streaming inference。

## 現有離線流程

    frames folder
    -> run_lingbot_mapping.py
    -> predictions.npz
    -> rebuilt_colored_map.ply
    -> 3D to 2D map
    -> A*

這適合離線分析，但不適合機器人 runtime，因為必須等完整資料跑完才有地圖。

## 新增線上 replay 流程

    predictions.npz
    -> frame 0
    -> frame 1
    -> frame 2
    -> incremental voxel map
    -> partial map.pgm / snapshot.ply
    -> current 2D occupancy grid

第一版不是重新跑模型，而是把已存好的 LingBot world_points 逐 frame replay。這樣可以獨立研究增量地圖更新。

## 新增檔案

- `Integrated_version/map/incremental_voxel_map.py`
  - runtime map data structure
  - voxel filtering
  - floor / obstacle / unknown classification
  - 2D occupancy grid projection
  - small obstacle component filtering
  - snapshot PLY export

- `Integrated_version/experiments/run_lingbot_online_replay.py`
  - reads `predictions.npz`
  - estimates floor height from bootstrap frames
  - feeds frames one by one
  - writes partial maps every N frames

## 執行方式

從 repository root 執行：

    conda run -n lingbot-map python Integrated_version/experiments/run_lingbot_online_replay.py \
      --write-every 5 \
      --sample-stride 8 \
      --output-dir outputs/scenes/scene_20260818/online_replay

快速測試：

    conda run -n lingbot-map python Integrated_version/experiments/run_lingbot_online_replay.py \
      --max-frames 12 \
      --write-every 4 \
      --sample-stride 12 \
      --output-dir outputs/scenes/scene_20260818/online_replay_test

產生 online replay 3D 俯視 viewer：

    conda run -n lingbot-map python Integrated_version/experiments/export_online_replay_3d_viewer.py \
      --replay-dir outputs/scenes/scene_20260818/online_replay \
      --max-points-per-frame 18000

輸出 3D viewer：

    outputs/scenes/scene_20260818/online_replay/online_replay_3d_top_viewer.html

產生 online replay 2D 對照 viewer：

    conda run -n lingbot-map python Integrated_version/experiments/export_online_replay_viewer.py \
      --replay-dir outputs/scenes/scene_20260818/online_replay \
      --scale 10

輸出 viewer：

    outputs/scenes/scene_20260818/online_replay/online_replay_viewer.html

## 輸出

最新地圖：

    outputs/scenes/scene_20260818/online_replay/map.pgm
    outputs/scenes/scene_20260818/online_replay/map.json
    outputs/scenes/scene_20260818/online_replay/snapshot.ply

每次 partial update：

    outputs/scenes/scene_20260818/online_replay/frame_000005/
    outputs/scenes/scene_20260818/online_replay/frame_000010/
    ...

統計摘要：

    outputs/scenes/scene_20260818/online_replay/online_replay_summary.json

## 目前測試結果

完整 43 frame replay：

    final map size: 74x50
    free cells: 888
    occupied cells: 870
    largest free component: 806

這代表地圖會隨資料流逐步長出來，已經可以作為後續 online mapping 的 baseline。

## 下一步

1. 前端新增 online replay viewer，顯示 map 隨 frame 更新。
2. 增加 frame-by-frame metrics：
   - free cells
   - occupied cells
   - largest free component
   - map changed cells
   - processing time per frame
3. 將 replay input 從 `predictions.npz` 換成 LingBot-MAP model session。
4. 建立真正 online session：
   - bootstrap first 8 frames
   - keep KV cache alive
   - feed one new frame per step
   - update incremental map
5. 最後才接相機與車體控制。

## 研究比較

可以比較三種方法：

    Offline full PLY -> 2D map
    Online replay from saved predictions -> incremental 2D map
    True online LingBot streaming -> incremental 2D map

專題的實驗重點應該放在：地圖逐步穩定的速度、可走區連通性、雜訊對路徑規劃的影響，以及是否能支援導航重新規劃。
