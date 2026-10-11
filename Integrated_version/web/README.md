# Web 模組

負責 HTTP API、模擬 Demo、操作頁面與靜態檢視器。不在瀏覽器程式碼中重做地圖、定位或規劃演算法。

- `demo_server.py`：整合展示入口，預設使用模擬車；啟動見根目錄 README。
- `server.py`：地圖規劃 API 與控制狀態入口。
- `http_responses.py`：共用 UTF-8 JSON/byte responses、Content-Length 與 no-cache headers。
- `index.html`、`app.js`、`styles.css`：主要操作介面。
- `demo/`：地圖/點雲資料檢視頁面。
- `DEMO_README.md`：Demo 參數與互動操作。

伺服器透過 `Integrated_version/localization/`、`Integrated_version/planner/` 和 `Integrated_version/storage/demo_storage.py` 使用後端功能。HTTP/狀態介面改動時，需一併檢查 API 回應與前端消費欄位。
