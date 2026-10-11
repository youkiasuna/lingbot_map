# 設定模組

- `navigation_20260818.json`：已保存導航地圖的建圖參數。
- `camera.json`：相機內參及 camera-to-base 外參；目前 `calibration_status` 為 `UNSET`。
- `vehicle.json`：差速車尺寸、安全門檻與速度限制；馬達輸出保持關閉。
- `validate_config.py`：檢查相機/車體設定結構。

相機/車體設定目前是待校正模板，runtime 尚未載入這些速度、安全或 command timeout 數值；`motor_output_enabled` 必須保持 `false`。結構驗證不代表校正完成或 watchdog 已接線。修改設定 schema 時，同步更新使用該 schema 的程式與文件。驗證未校正模板：

```powershell
conda run --no-capture-output -n lingbot-map python Integrated_version/configs/validate_config.py --allow-unset
```
