# Data Storage Audit

資料盤點基準：2026-09-15。2026-10-11 更新程式模組整理與驗證；分類搬移、路徑更新、指定清理與展示服務重啟依先前授權執行。

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
python3 -B Integrated_version/storage/demo_storage.py list
python3 -B Integrated_version/storage/demo_storage.py save outputs/tmp/<session>
python3 -B Integrated_version/storage/demo_storage.py discard outputs/tmp/<session>
```

## 尚未刪除

- `outputs/maps/20260804_dense.ply`：約 922 MiB。
- `outputs/maps/20260818_dense.ply`：約 5.8 GiB。
- 原始拍攝資料、正式研究結果、模型權重與 `.git` 歷史。

新架構與啟動指令見根目錄 `README.md`。資料清單位於 `outputs/manifests/`。

## 驗證

- （2026-09-15 當次驗證）19 項單元測試通過，包含原有實驗／導航及新增保存／目錄分類測試。
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

## 2026-10-11 程式模組整理與驗證

- `Integrated_version/` 現在依 map、localization、planner、runtime、web、hardware、experiments、configs、shared、storage、docs、tests 分區；各模組入口、責任與驗證命令見其 `README.md`。
- `experiments/README.md` 收斂為模組入口與文件索引；完整 ORB/PnP 與彩色定位研究規約保留於 `LOCALIZATION_BASELINE.md`，手機擷取和 online replay 各有獨立流程文件。
- 車控程式集中至 `Integrated_version/hardware/`；設定與 runtime contract 歸入 `configs/`、`docs/`；研究背景與回歸測試歸入 `experiments/`、`tests/`。
- 移除已由整合模組取代的 `map_localization_test/` 原型、舊 `visual_navigation/` 說明/設定入口，以及無引用的日期專用分析腳本；`Tony's project/` 保持不變。
- Windows 未授予 symlink 權限時，資料拆分使用 hard link，跨磁碟時複製；Demo 保存也採用 hard link/複製 fallback。fallback 不會以 session 清理動作刪除 raw capture 原件。
- planner、硬體與 Web 入口改用明確 package imports；ESP32 命令表及 TCP request/reply 集中於 `hardware/esp32_protocol.py`，避免 CLI、兩種 Web 控制入口各自實作協定。
- AST 引用盤點確認並移除 7 個未使用 imports；保留 `streaming_mapping_worker.py` 在 `TYPE_CHECKING` 下供 forward-reference 使用的 import。
- runtime、hardware、web、experiments 內部改用明確 `Integrated_version.*` 匯入；Windows 的 replay peak-RSS 指標改讀系統 peak working set，POSIX 仍使用 `resource`。
- 移除零引用的 `scan_bounds_and_floor()`、已被 managed session API 取代的 `make_session_dir()`，以及未接入 runtime 且與互動 mock 重複的 localization provider scaffold；replay runner 改以 `LocalPointCloudBackend` Protocol 表示 backend 邊界。
- 五個地圖輸出點改共用 `map/pgm_io.py`，runtime 三個相機入口共用 `runtime/video_source.py`；影像讀取與原子 JSON/NPZ 寫入集中於 `shared/`，map axis/mask/vector 幾何函式集中於 `map/geometry.py`。
- ORB/PnP localizer 移入 `localization/`，由 runtime、Web、實驗分析與測試共用，解除定位演算法對 `experiments/` 的反向依賴。
- LingBot-MAP 載入與 archive 輸出契約集中至 `runtime/lingbot_map_integration.py`，實驗 runner 共用它；runtime 不再反向匯入實驗 runner，模組依賴圖無跨模組循環。
- Demo/擷取 session 的暫存、保存與刪除安全規則集中至 `storage/demo_storage.py`，由 Web、capture 與 mapping pipeline 共用。
- 將只顯示串流的 `phone_video_receiver.py` 歸類為 `experiments/preview_phone_stream.py`；它不保存資料也不轉送串流，與持久化擷取及即時 mapping pipeline 的責任分開。
- 移除 dry-run-only `Esp32Adapter` 中沒有呼叫端的 watchdog state/query；車體 JSON 的 `command_timeout_s` 仍是未接線設定模板，文件已明確標示不會生效。
- 移除 `LiveMapManager` 沒有讀取端的 `map_ready` property/status 欄位；版本、點雲檔名與品質仍是已發布狀態契約。
- Web 兩個獨立 server 共用 `web/http_responses.py`，統一 UTF-8 JSON、Content-Length 和 no-cache headers，路由及錯誤語意仍各自維持。
- `shared/json_io.py` 統一 pose/manifest、實驗、Web API、LiveMapManager 的 JSON 寫入；`shared/npz_io.py` 統一即時地圖和 LingBot prediction archive 寫入，兩者皆使用唯一暫存檔、fsync 與失敗清理。
- 即時預覽影格改用具 `.jpg` 副檔名的唯一暫存檔；避免 OpenCV 把 `.tmp` 當成編碼格式，並確保編碼失敗不覆蓋上一張有效影格。
- 驗證：`python -m unittest discover -s Integrated_version/tests -v`，59 項通過，無 skip；含 occupancy builder、pose JSON、HTTP response、PGM/atomic JSON/NPZ、OpenCV JPEG 寫入、video source、geometry、pose reset、map write-failure recovery 與模組依賴白名單 fixtures。37 個應用 CLI 的 `--help` 從 repo 外工作目錄全數通過；`pip check`、`compileall` 和 `git diff --check` 亦通過。尚未執行 GPU 建圖、實機相機或車體測試。
