# Data Storage Audit

更新日期：2026-09-15。使用者已批准分類搬移、路徑更新、指定清理與展示服務重啟。

## 整理結果

| 類型 | 目前位置 | 約大小 |
| --- | --- | ---: |
| 整合程式、設定與測試 | `Integrated_version/` | 0.6 MiB |
| 原始影片、抽幀、手機拍攝與 query | `data/` | 1.6 GiB |
| 模型權重 | `models/lingbot-map.pt` | 4.4 GiB |
| 點雲與導航地圖 | `outputs/maps/` | 6.8 GiB |
| 正式場景結果 | `outputs/scenes/` | 239 MiB |
| 已保存手機建圖結果 | `outputs/live_sessions/` | 942 MiB |
| 舊版研究結果 | `outputs/archive/` | 61 MiB |
| 尚未確認的 Demo | `outputs/tmp/` | 隨使用變動 |
| Git 歷史 | `.git/` | 約 14 GiB，未更動 |

主程式仍位於原本功能資料夾，資料已移出：

- `videos/*.mp4` → `data/videos/`
- `videos/*_frames/` → `data/frames/`
- `lingbot-map-main/checkpoints/` → `models/`
- `lingbot-map-main/webcam_record_frames/` → `data/captures/webcam_record_frames/`
- `map_localization_test/outputs/` → `outputs/maps/`
- `Integrated_version/experiments/{scenes,archive,live_sessions,manifests,runs}/` → `outputs/` 下的同名資料夾
- 場景輸入、外部 query 與 session frames 實體存於 `data/`，輸出資料包以相對連結存取。

程式預設路徑、文件、JSON、CSV、影像連結與舊 NPZ 來源路徑已更新。
4 個 NPZ 僅更新 `frame_paths`；其餘陣列逐項 CRC 驗證相同。
新 NPZ schema 2 使用相對於 archive 所在目錄的影像路徑。

## 本次清理

- 刪除 139 個逐張查詢 HTML：ORB、colored、external query 結果及 `demo_query_*` viewer。
- 刪除 21 個 `results/demo/*_demo_result.json`，為互動操作輸出。
- 刪除 `scene_20260818/online_replay_test/`，內有 21 個測試輸出。
- 合計 181 個檔案，255,908,410 bytes，約 244 MiB。
- 保留研究 JSON、定位統計、參數、原始影像、8 個實驗總覽／回放 HTML 與舊地圖展示頁。
- 已移除 viewer 的研究摘要中，`viewer_html` 設為 null；研究數值未更動。

先前已完成的清理：15 個 Python 快取目錄、4 個無需保留的測試 session，以及 archive 中 2 份完全重複的 NPZ。
更早已清除約 42.9 GiB 中斷的 Git 暫存 pack，這次沒有再次清理 `.git`。

## 暫存與保存

- 新網頁 Demo、手機擷取、即時建圖先寫 `outputs/tmp/<唯一名稱>/`。
- 網頁使用「保存本次 Demo／捨棄本次 Demo」；CLI 結束選 `s/d/l`。
- 保存結果放 `outputs/saved_demos/`；CLI 即時流程保存至 `outputs/live_sessions/`。
- 保存時 frames 分離到 `data/captures/`，結果中保留相對連結。
- 尚未完成的建圖不允許保存／捨棄；沒有互動終端時保留待決定資料。
- 選「稍後」的資料仍占用空間，不會自動清除；模型權重不是暫存。
- 正式研究與低階 `--output-dir` 指令仍是明確保存。
- 批次 ORB 預設不產生逐張 HTML，需明確加 `--write-viewers`。

```bash
python3 -B Integrated_version/experiments/demo_storage.py list
python3 -B Integrated_version/experiments/demo_storage.py save outputs/tmp/<session>
python3 -B Integrated_version/experiments/demo_storage.py discard outputs/tmp/<session>
```

## 尚未刪除

- `outputs/maps/20260804_dense.ply`：約 922 MiB。
- `outputs/maps/20260818_dense.ply`：約 5.8 GiB。
- 原始拍攝資料、正式研究結果、模型權重與 `.git` 歷史。

新架構與啟動指令見根目錄 `README.md`。資料清單位於 `outputs/manifests/`。

## 驗證

- 19 項單元測試通過，包含原有實驗／導航及新增保存／目錄分類測試。
- 所有場景影像連結與 4 個 NPZ 的來源影像路徑有效。
- 18115 已使用新版啟動；真實場景 query 定位、規劃 API、7 個總覽 HTML 與分類 PLY 回應正常。
- 保存／捨棄 API 通過；正式導航地圖與研究結果檔案 hash 前後一致。
- 本次沒有重新連接手機、執行 GPU 建圖或進行瀏覽器畫面自動測試。
- 總專案約 28 GiB，包含約 14 GiB Git 歷史。

## Git 保存範圍

- 提交程式、設定 JSON、網頁原始 HTML、測試、文件與小型 `room_ascii.ply` 測試樣本。
- 排除 `data/`、`models/`、`outputs/`，以及搬移前的 scenes、runs、archive、live_sessions、manifests 等舊資料路徑。
- 170 個仍留在 Git 暫存區的舊資料項目已移除，本機資料不受影響。
- 大型模型／NPZ／PLY、執行狀態、環境與快取亦有補充屏蔽規則。
- 本機工具快照仍可能保留舊資料，但不會隨正常推送 `main` 上傳；本次未清除快照或改寫既有提交歷史。
