# Experiments 模組

放可直接執行的研究流程、資料擷取與結果分析。通用演算法位於 `map/`、`localization/`、`planner/`；長生命週期即時協調位於 `runtime/`；session 保存與捨棄由 `storage/` 管理。

## 入口

| 工作 | 入口 |
| --- | --- |
| 一鍵定位研究流程 | `run_research_pipeline.py` |
| LingBot-MAP 建圖與 archive | `run_lingbot_mapping.py` |
| Mapping/query 影像切分 | `prepare_frame_split.py` |
| 手機串流預覽（不保存） | `preview_phone_stream.py` |
| 手機串流保存 | `capture_phone_stream.py` |
| 邊擷取邊建圖 | `run_live_mapping_pipeline.py` |
| 回放／線上 mapping 實驗 | `run_live_mapping_replay.py`、`run_lingbot_online_replay.py` |
| TSDF mesh | `build_tsdf_mesh.py` |
| query 定位與檢視 | `analyze_external_queries.py`、`localize_query_in_3d_viewer.py`、`colored_pointcloud_localizer.py` |
| 即時場景/回放檢視輸出 | `export_live_scene_json.py`、`export_online_replay_3d_viewer.py`、`export_online_replay_viewer.py` |
| 研究資料盤點 | `scan_research_data.py`，只分類/列出候選，不自動刪除資料 |

所有 CLI 從 repository root 啟動；輸入放 `data/`、模型放 `models/`、產物放 `outputs/`。流程只重用或更新其明確指定的輸出，不自動清除未管理的研究資料。session 的保存／捨棄規則見 [`storage/`](../storage/README.md)。

## 文件

- [Localization baseline 與研究契約](LOCALIZATION_BASELINE.md)：mapping/query split、ORB/PnP、彩色點雲方法與比較規約。
- [Online mapping replay](ONLINE_MAPPING_RESEARCH.md)：增量回放流程、輸出和限制。
- [Phone stream capture](PHONE_STREAM_CAPTURE.md)：手機端串流、電腦端擷取與保存流程。
- [Live mapping pipeline](LIVE_MAPPING_PIPELINE.md)：串流擷取和持續建圖入口。
- [研究背景與資料契約](RESEARCH_CONTEXT.md)：研究問題、座標與輸入假設。
- 根目錄 [Ground Truth readiness](../../GROUND_TRUTH_EXPERIMENT_PLAN.md)：獨立重訪定位評估尚缺條件與現場檢查表。

## 驗證

```powershell
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -v
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_analyze_external_queries.py" -v
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_data_layout.py" -v
```

離線測試不需要相機、ESP32、模型權重或大型研究資料；通過測試不代表 GPU、串流或實機已驗證。
