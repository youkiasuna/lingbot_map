# LingBot Map 專題

## 目錄

| 位置 | 用途 |
| --- | --- |
| `Integrated_version/` | 整合程式：建圖處理、定位、規劃、網頁、實驗工具與測試 |
| `car/car/` | ESP32 韌體、手動遙控與手機影像接收 |
| `lingbot-map-main/` | LingBot-MAP 原始程式 |
| `map_localization_test/` | 早期地圖與導航測試程式 |
| `visual_navigation/` | 導航設計文件與設定 |
| `data/` | 原始影片、抽幀、手機拍攝、場景輸入與查詢照片 |
| `models/` | 模型權重，保留 `lingbot-map.pt` |
| `outputs/maps/` | 點雲與導航地圖，包括仍保留的兩份 dense PLY |
| `outputs/scenes/` | 正式建圖資料包與定位研究結果 |
| `outputs/live_sessions/` | 已保留的手機建圖結果 |
| `outputs/archive/` | 舊研究版本，保留部分展示用總覽 |
| `outputs/tmp/` | 尚未決定保存／捨棄的 Demo 暫存 |
| `outputs/saved_demos/` | 在網頁明確保存的 Demo |

資料包內的 `inputs/`、`external_query_images/`、`frames/` 可能是指向 `data/` 的相對連結，
不是重複存一份。不要只備份 `outputs/`；要一起保留對應的 `data/`。

## 網頁 Demo

從專案根目錄執行：

```bash
conda run --no-capture-output -n lingbot-map python -B Integrated_version/web/demo_server.py \
  --port 18115 --snap-localization-to-free
```

開啟 <http://127.0.0.1:18115>。目前為模擬展示，不會自動驅動實車。
每次啟動會建立獨立暫存，正式場景與導航地圖不會被定位／模擬操作覆寫。
停止掃描並等待建圖結束後，選「保存本次 Demo」或「捨棄本次 Demo」。
關閉伺服器不代表已保存或已刪除，尚未決定的資料會留在 `outputs/tmp/`。

## IP Webcam 建圖

```bash
conda run --no-capture-output -n lingbot-map python -B Integrated_version/experiments/run_live_mapping_pipeline.py \
  --url http://192.168.50.98:8080/video \
  --session-name ipwebcam --fps 5 --batch-frames 30 --process-every 30 \
  --max-frames 60 --camera-num-iterations 1 --use-sdpa
```

實際目錄會印在終端，名稱帶唯一後綴，不會覆蓋先前 session。
結束可輸入 `s` 保存、`d` 捨棄、`l` 稍後決定；沒有互動終端時會保留待決定資料。
保存會將影像移到 `data/captures/`、結果放到 `outputs/live_sessions/`。

```bash
python3 -B Integrated_version/experiments/demo_storage.py list
python3 -B Integrated_version/experiments/demo_storage.py save outputs/tmp/<session>
python3 -B Integrated_version/experiments/demo_storage.py discard outputs/tmp/<session>
```

以上 `<session>` 請使用 `list` 顯示的實際目錄名；`discard` 會刪除該次全部暫存。

## 研究與保存

正式研究使用 `Integrated_version/experiments/run_research_pipeline.py`，預設讀取
`data/frames/20260818_frames/` 與 `models/lingbot-map.pt`，結果寫入 `outputs/scenes/scene_20260818/`。
研究指令的輸出是明確保存，和互動 Demo 的暫存不同。

批次 ORB 預設只寫研究 JSON；需要逐張 HTML 時，對 `analyze_external_queries.py` 加 `--write-viewers`。
保存條件與清理紀錄見 [DATA_STORAGE_AUDIT.md](DATA_STORAGE_AUDIT.md)。
Git 只保存程式、設定、測試與文件；`data/`、`models/`、`outputs/` 及舊資料目錄均已排除，舊實驗資料也已從暫存追蹤清單移除。
本機資料仍保留。這次沒有改寫 Git 歷史，因此 `.git` 的既有物件不會因忽略規則而自動縮小。
