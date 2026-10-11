# 規劃模組

負責在已建立的 occupancy grid 上產生路徑、模擬差速車軌跡，以及 Pure Pursuit 控制量計算。模組不載入相機影像，不直接連 ESP32。

- `grid_navigation.py`：格網座標轉換、A*、障礙距離成本與路徑簡化。
- `pure_pursuit.py`：由 pose/path 計算追蹤命令。
- `simulate_vehicle_path.py`：離線車體運動與碰撞檢查。

輸入地圖由 `map/` 產生；線上狀態協調由 `runtime/` 負責。路徑 JSON/座標慣例見 [runtime contract](../docs/NAVIGATION_RUNTIME_CONTRACT.md)。

## 驗證

```powershell
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_grid_navigation.py" -v
```
