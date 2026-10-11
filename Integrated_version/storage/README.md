# Session 儲存

集中管理 Demo、手機擷取與 live mapping session 的暫存、保存和捨棄生命週期。

- `demo_storage.py`：建立暫存 session、保存至使用者指定位置，或在路徑驗證後捨棄。Windows 不支援 symlink 時使用 hard link/複製 fallback；捨棄 session 不會沿連結刪除 raw capture 原件。
- Web 與實驗 runner 呼叫同一套 session API；HTTP handler 不自行實作檔案搬移或刪除。

## 驗證

```powershell
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_demo_storage.py" -v
```
