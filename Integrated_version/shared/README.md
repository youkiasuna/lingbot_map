# 共用工具

只放被多個領域模組使用、且不屬於特定演算法或執行流程的共用 I/O。

- `image_io.py`：透過 OpenCV 支援 Unicode 路徑讀取 BGR 影像，供定位和點雲重建工具使用。
- `json_io.py`：以唯一同目錄暫存檔、flush/fsync 和原子替換輸出 JSON；替換失敗時清理暫存檔，避免半寫入和併發暫存名稱衝突。
- `npz_io.py`：以相同的唯一暫存/原子替換規則輸出壓縮 NumPy archive，供 runtime 與模型整合流程共用。

新增工具前先確認至少有跨模組呼叫需求；單一領域的 helper 留在該領域，不把此目錄當成未分類收納處。

## 驗證

```powershell
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_image_io.py" -v
conda run --no-capture-output -n lingbot-map python -m unittest discover -s Integrated_version/tests -p "test_shared_io.py" -v
```
