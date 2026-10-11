# 測試模組

此處是整個整合應用的離線回歸測試，包括資料保存、研究 wrapper、定位、規劃與 runtime。測試使用小型合成資料，不需模型權重、相機、ESP32 或大型 `data/` / `outputs/`。所有 `test_*.py` 集中在此處，`experiments/` 只放可執行流程和分析工具。

## 測試索引

- 地圖與規劃：`test_topdown_map.py`、`test_grid_navigation.py`、`test_incremental_mapping.py`、`test_shared_geometry.py`。
- Runtime 與 backend：`test_live_mapping_architecture.py`（map 寫入失敗時保留版本）、`test_live_pointcloud_runtime.py`（JPEG 寫入與失敗保護）、`test_online_mapping_navigation.py`、`test_local_pointcloud_backend.py`、`test_realtime_navigation_core.py`、`test_lingbot_map_integration.py`、`test_process_metrics.py`。
- 定位與資料契約：`test_localization_contract.py`、`test_orb_keyframe_localizer.py`、`test_localize_query_in_3d_viewer.py`。
- 實驗工具與共用 I/O：`test_analyze_external_queries.py`、`test_data_layout.py`、`test_image_io.py`、`test_shared_io.py`（格式、失敗清理與 atomic replace）。
- Session 保存安全：`test_demo_storage.py`（路徑隔離、raw capture 保護、保存 fallback）。
- Web HTTP response：`test_web_http_responses.py`（UTF-8 JSON、狀態碼、Content-Length 與 no-store headers）。
- 設定、硬體與套件邊界：`test_config_validation.py`、`test_esp32_protocol.py`、`test_package_imports.py`（限定跨模組依賴白名單並檢查無環）。

完整測試：

```powershell
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -v
```

只跑單一檔案：

```powershell
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_grid_navigation.py" -v
```

測試按照領域命名；新增模組行為時，優先把測試放在此處，並在相關模組 README 補上對應命令。套件匯入測試也會避免跨模組回退成裸名稱。通過測試代表離線契約成立，不等同 GPU、實際相機串流或硬體閉迴路驗證。

Windows 未啟用 Developer Mode/符號連結權限時，資料拆分會改用 hard link，跨磁碟時複製檔案；Demo 保存則以 hard link/複製維持 `frames` 存取。相關測試會直接驗證 fallback，不需啟用 Developer Mode。
