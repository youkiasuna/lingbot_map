# 定位模組

負責姿態資料格式、視覺定位器及定位結果的接受門檻。此處不執行 A*、不管理影片串流，也不發送硬體命令。

- `localizer_interface.py`：`PoseSample` 與 JSON file publisher 契約。
- `pose_gate.py`：依有效性、信心和時間新鮮度判斷姿態能否供下游使用。
- `mock_pose_tracker.py`：離線互動測試用姿態來源，不是視覺定位器。
- `orb_keyframe_localizer.py`：ORB keyframe retrieval、2D-3D correspondence、PnP/RANSAC 和 pose 輸出；runtime 與 Web 共用此實作。

姿態 JSON 欄位和座標慣例見 [runtime contract](../docs/NAVIGATION_RUNTIME_CONTRACT.md)。

## 驗證

```powershell
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_realtime_navigation_core.py" -v
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_orb_keyframe_localizer.py" -v
```
