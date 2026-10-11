# 地圖模組

負責把點雲轉為可供定位展示和路徑規劃使用的地圖資料。此模組不擷取影像、不估計相機姿態，也不管理網頁或硬體。

## 主要流程

```text
PLY -> clean/calibrate -> floor/obstacle classification -> occupancy grid
                                                   -> obstacle distance field
```

- `build_topdown_map.py`：PLY 投影成 2D PGM/JSON。
- `clean_point_cloud_20260818.py`、`calibrate_floor_plane.py`：點雲整理與地板座標校正。
- `build_3d_navigation_map.py`、`build_rebuilt_navigation_map.py`、`build_mesh_navigation_map.py`：由不同點雲輸入建立導航地圖。
- `build_obstacle_distance.py`：計算距障礙物距離場，供風險感知規劃使用。
- `pgm_io.py`：供所有靜態/增量建圖入口共用的 binary PGM writer。
- `geometry.py`：共用 signed-axis 映射、numpy mask 膨脹與向量運算。
- `incremental_voxel_map.py`：增量 voxel 地圖資料結構；線上協調由 `runtime/` 負責。
- `export_height_color_viewer.py`：輸出點雲/路徑檢視 HTML。

舊的 `analysis_20260818_floor_obstacle.py` 是無引用的日期專用實驗腳本，已移除；重建點雲請用 `build_rebuilt_navigation_map.py`，已校正點雲請用 `build_3d_navigation_map.py`。

CLI 範例和輸出 schema 見 [核心 README](../README.md)。資料輸出指定至根目錄 `outputs/`，不要把產物寫回原始碼目錄。

## 驗證

```powershell
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_incremental_mapping.py" -v
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_topdown_map.py" -v
```

建圖演算法目前主要由整合/實驗流程使用；新增轉換規則時應加小型 fixture 測試，並保留座標軸與單位說明。
