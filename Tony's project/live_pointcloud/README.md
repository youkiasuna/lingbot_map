# Tony live point-cloud test

這個資料夾只放 Tony 的測試入口，不修改 `lingbot-map-main`。

## Run

把 `PHONE_IP` 換成手機或 IP camera 的內網位址：

```bash
python "Tony's project/live_pointcloud/run_live_pointcloud.py" \
  --url http://192.168.50.98:8080/video
```

預設設定：

- 每秒保存 5 張影像。
- 第一次累積 30 張後重建。
- 之後每新增 30 張再更新一次。
- 輸出放在 `Tony's project/live_pointcloud/outputs/sessions/`。
- 瀏覽器入口是 `http://127.0.0.1:18088/latest.html`。

內網其他電腦要看時，使用腳本印出的 `LAN viewer page`。

## Common options

```bash
python "Tony's project/live_pointcloud/run_live_pointcloud.py" \
  --url http://PHONE_IP:8080/video \
  --fps 5 \
  --batch-frames 30 \
  --process-every 30 \
  --rotate none
```

如果手機畫面方向不對，可把 `--rotate none` 換成 `cw90`、`ccw90` 或 `180`。
