# 硬體模組

此模組集中 ESP32 韌體、人工控制器及 Python 硬體 adapter。它與 `runtime/` 分開，讓離線模擬和實際 I/O 有清楚邊界。

- `esp32_motor_control.ino`：ESP32 TCP 單字元手動移動協定。
- `pc_controller.py`、`web_controller.py`：人工控制端；不是自主導航控制器。
- `esp32_protocol.py`：共用 TCP 命令表與 newline-terminated request/reply 實作。
- `esp32_adapter.py`：runtime 可使用的硬體介面。

## 手動操作

上傳韌體前，將 `esp32_secrets.example.h` 複製為本機 `esp32_secrets.h`，填入 Wi-Fi SSID/密碼；本機檔案已加入 Git 忽略規則。不要把真實憑證寫回 `.ino` 或提交到 Git。若舊憑證曾推送至遠端，請更換密碼；從目前版本刪除不會清除 Git 歷史。

將 `esp32_motor_control.ino` 上傳到 ESP32，電腦連上 `CarAP` 後，在專案根目錄執行：

```powershell
conda run -n lingbot-map python Integrated_version/hardware/pc_controller.py --command forward
conda run -n lingbot-map python Integrated_version/hardware/web_controller.py --ip 192.168.4.1 --port 8000
```

瀏覽器控制頁面位於 <http://127.0.0.1:8000>。`web_controller.py` 可用 `--video-url` 在控制頁顯示影像；若串流透過 SSH 轉送，將其設為轉送端網址，例如 `http://127.0.0.1:18080/video`。純預覽手機影像、不保存 frames 時，使用 `Integrated_version/experiments/preview_phone_stream.py`。

ESP32 接受單字元 `F`（前進）、`B`（後退）、`L`（左轉）、`R`（右轉）、`S`（停止）。瀏覽器支援方向鍵與空白鍵停止。

`web_controller.py` 的速度滑桿預設送出 `V<數值>`；隨附的 `esp32_motor_control.ino` 尚未實作此命令，馬達使能腳固定為 HIGH。只有搭配支援 `--speed-command-template` 的其他韌體時才使用速度滑桿；目前控制協定與實際速度控制未經實車驗證。

根目錄 `README.md` 的 Demo 僅模擬，不會驅動這些硬體。設定中的馬達輸出預設關閉；車體尺寸、相機外參或閉迴路實車能力未校正/驗證時，不得啟用自主輸出。
