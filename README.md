# LingBot Map

## 專案模組

| 模組 | 責任 | 入口與說明 |
| --- | --- | --- |
| `Integrated_version/map/` | 點雲清理、座標校正、2D/3D 導航地圖與障礙距離場 | [模組說明](Integrated_version/map/README.md) |
| `Integrated_version/localization/` | ORB/PnP 視覺定位、姿態介面與信心門檻 | [模組說明](Integrated_version/localization/README.md) |
| `Integrated_version/planner/` | A*、Pure Pursuit、車體路徑模擬 | [模組說明](Integrated_version/planner/README.md) |
| `Integrated_version/runtime/` | 串流、增量建圖、定位與導航狀態協調 | [模組說明](Integrated_version/runtime/README.md) |
| `Integrated_version/web/` | Demo/API、地圖操作介面與檢視器 | [模組說明](Integrated_version/web/README.md) |
| `Integrated_version/hardware/` | ESP32 韌體、手動控制器與硬體 adapter | [模組說明](Integrated_version/hardware/README.md) |
| `Integrated_version/experiments/` | LingBot 執行流程、串流預覽/擷取、研究與結果分析 | [模組說明](Integrated_version/experiments/README.md) |
| `Integrated_version/configs/` | 導航、相機、車體設定及設定驗證 | [模組說明](Integrated_version/configs/README.md) |
| `Integrated_version/shared/` | 跨模組影像讀取與原子 JSON/NPZ I/O | [模組說明](Integrated_version/shared/README.md) |
| `Integrated_version/storage/` | Demo/capture session 暫存、保存與捨棄 | [模組說明](Integrated_version/storage/README.md) |
| `Integrated_version/tests/` | 離線回歸測試與模組邊界檢查 | [模組說明](Integrated_version/tests/README.md) |
| `Integrated_version/docs/` | Runtime 契約與較長流程說明 | [文件索引](Integrated_version/docs/README.md) |
| `lingbot-map-main/` | 上游 LingBot-MAP 原始碼；wrapper 依此路徑載入 | [上游文件](lingbot-map-main/README.md) |
| `data/`、`models/`、`outputs/` | 本機輸入、模型權重、執行結果；不納入 Git | [資料保存規則](DATA_STORAGE_AUDIT.md) |

`Integrated_version/README.md` 是核心架構索引。每個模組的 README 只描述該模組的入口、界線和驗證方式，避免為了找一個功能掃讀整個專案。

舊的 `map_localization_test/` 是早期獨立原型，已由 `Integrated_version/map/`、`planner/`、`localization/` 和 `web/` 取代，不再維護第二套程式。`visual_navigation/` 的設定與姿態契約已併入核心設定與文件。車控程式集中在 `Integrated_version/hardware/`。

`Tony's project/` 是獨立保留區，不屬於上述模組整理範圍。

## 執行

模擬 Demo 使用本機資料（不納入 Git），啟動前需準備導航地圖 `map.pgm`、`map.json`，以及場景的 `mapping/predictions.npz`。預設位置分別為 `outputs/maps/20260818_navigation_rebuilt_voxel/` 和 `outputs/scenes/scene_20260818/`；定位查詢影像放在場景的 `inputs/query_images/`。可用 `--map-dir`、`--scene-dir` 指向其他資料夾。

使用已建立的 Conda 環境啟動模擬 Demo：

```powershell
conda run --no-capture-output -n lingbot-map python -B Integrated_version/web/demo_server.py --port 18115 --snap-localization-to-free
```

開啟 <http://127.0.0.1:18115>。Demo 預設為模擬模式，不會驅動實車。

執行回歸測試：

```powershell
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -v
```

驗證相機/車體設定結構（目前校正值仍未設定）：

```powershell
conda run --no-capture-output -n lingbot-map python Integrated_version/configs/validate_config.py --allow-unset
```

手機即時建圖、研究資料位置及保存/捨棄操作見 [experiments README](Integrated_version/experiments/README.md)。
