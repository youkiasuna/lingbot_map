# 行進中增量建圖與即時導航架構

## 目標

本雛形支援：

開機無既有 3D 地圖 -> 探索建立局部地圖 -> Viewer 顯示地圖增加 -> 地圖達標 -> 啟動導航 -> 行進中背景更新 -> Viewer 顯示車輛位置、yaw 與軌跡。

這是 Level 2：incremental local mapping + visual navigation，不是完整 global SLAM，也不代表已完成真實 autonomous driving。

## 新增模組

- runtime/mapping_state_machine.py：管理 BOOT、探索、導航、定位遺失與復原狀態。
- runtime/live_map_manager.py：管理 map version、品質、座標規則與原子 JSON 輸出。
- runtime/live_viewer_state.py：發布 Viewer 所需的 pose、path、status。
- tests/test_live_mapping_architecture.py：測試版本管理、失敗更新保護與狀態門檻。

既有 realtime_navigation.py、ORB、A*、Pure Pursuit 暫時保留，不直接改寫既有 RTSP 流程。

## 狀態流程

BOOT -> MAPPING_ONLY -> MAP_READY -> NAVIGATING

定位遺失時：

NAVIGATING -> LOCALIZATION_LOST -> RECOVERY_MAPPING -> MAP_READY

地圖沒有達到品質門檻前，不得進入導航。定位失敗時必須保持 safety stop。

## Live map 輸出

LiveMapManager 會在指定輸出資料夾產生：

- live_map.json：map version、品質與座標規則。
- live_points.json：目前局部點雲取樣。
- live_pose.json：position、yaw、confidence 與狀態。
- live_path.json：X/Z 平面路徑。
- live_status.json：Viewer 與 runtime 狀態。

所有 JSON 使用暫存檔加 os.replace 發布，避免 Viewer 讀到半份檔案。無效更新不增加 map version，也不覆蓋上一份有效地圖。

座標規則固定為：

- vertical axis: -Y
- navigation plane: X/Z
- position mapping: x_m = position_xyz[0], y_m = position_xyz[2]

## 建議即時頻率

| 元件 | 頻率 |
| --- | ---: |
| RTSP camera | 10–15 Hz |
| visual localization | 5–10 Hz |
| local map update | 每 5–10 幀一次，背景執行 |
| A* replanning | 1–5 Hz 或地圖顯著改變 |
| Pure Pursuit | 10–20 Hz |
| Viewer pose | 5–10 Hz |
| 點雲更新 | 2–5 Hz |

不能每幀重新執行完整 LingBot-MAP。應使用固定大小 sliding window，避免處理時間隨歷史影像無限增加。

## 單眼限制

單眼系統的絕對尺度不能直接假設。若要使用公尺單位導航，仍需要 LingBot reconstruction scale、已知車體尺寸、地面高度、IMU/輪速或其他尺度來源。

目前 RTSP 測試曾出現 inlier_count=0，因此這個架構雛形不能宣稱定位已驗證。實際 GPU、RTSP 長時間執行、局部點雲產生器與 Viewer 串接，必須在使用者的 RTX 3090 主機另行測試，目前為 NOT VERIFIED。

## 下一階段整合順序

1. 將探索階段產生的局部點雲接到 publish_map_update()。
2. 將 ORB/LightGlue pose 接到 LiveViewerState.update()。
3. 將 map_version 與導航 grid 綁定，地圖更新後才低頻率重新規劃。
4. 再將 realtime_navigation.py 接入 state machine。
5. 在真實馬達介面接通前維持 dry-run 與 safety stop。

## 測試

執行：

    PYTHONPATH=Integrated_version python -m unittest discover -s Integrated_version/tests -v

或：

    python -m py_compile Integrated_version/runtime/live_map_manager.py Integrated_version/runtime/mapping_state_machine.py Integrated_version/runtime/live_viewer_state.py

這些測試只驗證架構契約，不代表 RTSP、GPU、LingBot-MAP 或實際車輛運動已驗證。
