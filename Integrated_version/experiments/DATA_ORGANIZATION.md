# Research Data Organization

2026-09-15 已完成程式與資料分離。完整入口見根目錄 `README.md`，清理紀錄見 `DATA_STORAGE_AUDIT.md`。

| 類型 | 位置 | 保存原則 |
| --- | --- | --- |
| 程式、設定、測試 | `Integrated_version/`、`car/`、`lingbot-map-main/` 等 | 版本管理 |
| 原始影片 | `data/videos/` | 保留，抽幀來源 |
| 抽幀 | `data/frames/` | 場景連結正在使用，不直接刪除 |
| 手機原始影像 | `data/captures/` | 確認保存後保留，不能由點雲還原 |
| 場景輸入與外部 query | `data/scenes/`，舊版為 `data/archive/` | 保留 |
| 模型權重 | `models/` | 保留一份 |
| 正式場景 | `outputs/scenes/` | 保留 mapping、預處理影像、研究 JSON、參數與總覽 |
| 點雲／導航地圖 | `outputs/maps/` | 目前展示有引用，多版本保留 |
| 舊結果 | `outputs/archive/` | 研究 JSON、參數與必要總覽保留 |
| 即時成果 | `outputs/live_sessions/` | 已確認保存的手機實驗 |
| 網頁 Demo 成果 | `outputs/saved_demos/` | 明確保存後才放入 |
| 未決定的 Demo | `outputs/tmp/` | 明確保存或捨棄，不默默刪除 |
| 資料盤點 | `outputs/manifests/` | 可重新產生 |

## 資料包與連結

`outputs/scenes/<scene>/inputs` 連到 `data/scenes/<scene>/inputs`。
`outputs/scenes/<scene>/external_query_images` 連到原始查詢照片。
`outputs/live_sessions/<session>/frames` 連到 `data/captures/<session>/frames`。
預處理影像必須與同一次 mapping 的 `predictions.npz` 配對保存。
備份結果時必須一併保存連結指向的原始資料。

## 哪些結果值得保留

- 正式研究：保留原始輸入、參數、NPZ、PLY、定位 JSON／統計與必要總覽。
- 互動 Demo：先暫存；檢查重建品質、影像內容、失敗原因與研究用途後再選保存。
- 不需要的 Demo：選捨棄，包含該次原始擷取影像；既有正式資料不會跟著刪除。
- 逐張 HTML：預設不批次產生，需要時使用 `analyze_external_queries.py --write-viewers`。
- 沒有選擇：保留在 `outputs/tmp/`，仍占用硬碟，並非系統自動清理的 `/tmp`。

```bash
python3 -B Integrated_version/experiments/demo_storage.py list
python3 -B Integrated_version/experiments/scan_research_data.py
```

`data/`、`models/`、`outputs/` 及搬移前的舊資料目錄已加入 `.gitignore`；舊實驗資料已從 Git 暫存追蹤清單移除，本機資料保留。既有提交歷史未改寫。
