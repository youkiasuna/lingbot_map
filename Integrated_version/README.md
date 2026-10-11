# 核心應用架構

## 資料流

```text
camera frames -> runtime/mapping -> map artifacts -> localization -> planner
                                                   -> web viewer/API
planner -> navigation state -> hardware adapter (disabled by default)
```

`Integrated_version/` 是本專案唯一持續維護的整合應用。領域程式放在對應模組；跨領域流程由 `runtime/` 或 `experiments/` 協調。`lingbot-map-main/` 是上游模型程式，不在此處複製或改寫。

內部跨模組引用使用 `Integrated_version.<module>` 套件路徑；CLI 腳本仍可從 repository root 直接執行，並由入口明確補上 repository root，不以 planner/config 等子目錄建立裸模組別名。

## 模組索引

| 目錄 | 責任 | 邊界 |
| --- | --- | --- |
| `map/` | 點雲與導航地圖轉換 | 不管理相機串流或網頁狀態 |
| `localization/` | 視覺定位、姿態介面與接受門檻 | 不規劃路徑、不發送馬達命令 |
| `planner/` | 格網路徑、追蹤控制與離線模擬 | 不讀取相機、不直接連 ESP32 |
| `runtime/` | 即時/增量流程、元件生命週期與狀態協調 | 透過領域模組呼叫演算法 |
| `web/` | HTTP API、Demo UI、地圖檢視 | UI/HTTP 不承載地圖演算法 |
| `hardware/` | ESP32、手動控制與硬體 adapter | 自主馬達輸出仍受安全設定控制 |
| `experiments/` | 可執行研究流程、擷取、分析及資料保存 | 實驗輸出寫入根目錄 `outputs/` |
| `configs/` | 版本化設定與設定結構驗證 | 校正值未設定不代表硬體已校正 |
| `shared/` | 跨模組共用的影像讀取與原子 JSON/NPZ I/O | 不放領域流程或執行入口 |
| `storage/` | Demo 與擷取 session 的保存/捨棄生命週期 | 驗證 session 路徑，保護 raw capture 原件 |
| `tests/` | 跨模組回歸測試 | 使用 unittest；不需要相機或 ESP32 |
| `docs/` | 系統契約與較長的流程說明 | 模組操作指令放在模組 README |

各模組的細節與單獨檢查方式見該目錄的 `README.md`。

## 主要工作入口

- 模擬網頁 Demo：`web/demo_server.py`
- 手動地圖/規劃 API：`web/server.py`
- 即時手機建圖：`experiments/run_live_mapping_pipeline.py`
- 研究建圖：`experiments/run_research_pipeline.py`
- 線上 mapping/replay runtime：`runtime/online_mapping_navigation.py`
- 回歸測試：`python -m unittest discover -s Integrated_version/tests -v`

## 跨模組契約

- 導航格網與座標轉換由 `map/` 產生、`planner/` 消費。
- 姿態資料格式與信心門檻由 `localization/` 定義；契約見 `docs/NAVIGATION_RUNTIME_CONTRACT.md`。
- `runtime/` 負責串接狀態；HTTP/UI 由 `web/` 呈現。
- 依賴維持單向無環：`shared/` 不依賴領域模組，`runtime/` 不反向匯入 `experiments/`，外層流程可呼叫 runtime 與領域模組；`test_package_imports.py` 會檢查循環依賴與模組依賴白名單。
- 實驗和 Demo 資料預設寫到根目錄 `outputs/`；原始資料在 `data/`、權重在 `models/`，三者不進 Git。
- 硬體輸出預設停用；不可由 Demo 的成功狀態推論為實車閉迴路已驗證。

## 測試

```powershell
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -v
```

測試通過只表示程式契約與離線行為通過，不代表 GPU 推論、長時間相機串流或實車運動已驗證。
