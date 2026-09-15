# Phone Stream Capture

階段 1 目標：先把手機相機變成可重播、可分析的 frame stream。

這一步不跑 LingBot-MAP，也不控制車。只負責：

    phone camera stream
    -> OpenCV VideoCapture
    -> live session frames
    -> capture_manifest.json

## 手機端

Android 可以先用 IP Webcam / DroidCam / Iriun Webcam。

常見 MJPEG URL：

    http://PHONE_IP:8080/video

手機和電腦必須在同一個網路，或經過 port forwarding。

## iPhone 方法

iPhone 也可以做階段 1，但重點是要拿到 OpenCV 能讀的影像 URL。

推薦方式 A：RTSP / IP Camera App

可以找支援 RTSP 或 MJPEG 的 iPhone app，例如：

    RTSP Camera
    IP Camera Lite
    Larix Broadcaster
    Iriun Webcam
    EpocCam

如果 app 提供 RTSP URL，通常長這樣：

    rtsp://IPHONE_IP:8554/live
    rtsp://IPHONE_IP:8554/stream

執行 capture：

    conda run -n lingbot-map python Integrated_version/experiments/capture_phone_stream.py \
      --url rtsp://IPHONE_IP:8554/live \
      --session-name iphone_test \
      --fps 5 \
      --max-frames 30

如果 app 提供 MJPEG URL，通常長這樣：

    http://IPHONE_IP:8080/video
    http://IPHONE_IP:8080/mjpeg

執行 capture：

    conda run -n lingbot-map python Integrated_version/experiments/capture_phone_stream.py \
      --url http://IPHONE_IP:8080/video \
      --session-name iphone_test \
      --fps 5 \
      --max-frames 30

推薦方式 B：iPhone 當電腦 Webcam

如果你用 macOS 的 Continuity Camera、EpocCam、Iriun Webcam，iPhone 可能會變成電腦上的 webcam device。這種情況目前 `capture_phone_stream.py` 主要吃 URL，之後可以再加 `--camera-index 0` 支援直接讀 webcam。

目前 Linux / 遠端主機環境下，最建議還是用方式 A：讓 iPhone app 直接提供 RTSP 或 MJPEG URL。

注意事項：

- iPhone 和電腦要在同一個 Wi-Fi。
- 如果電腦在遠端主機或 Docker/SSH 環境，要確認 port 有轉發。
- iPhone 請固定橫向或直向，不要拍攝中途旋轉。
- 如果畫面方向錯，用：

    --rotate cw90
    --rotate ccw90
    --rotate 180

## 電腦端 Capture

從 repository root 執行：

    cd /media/ee303/1tb/lingbot_map

基本測試，存 30 張：

    conda run -n lingbot-map python Integrated_version/experiments/capture_phone_stream.py \
      --url http://PHONE_IP:8080/video \
      --session-name phone_test \
      --fps 5 \
      --max-frames 30

如果手機畫面方向不對：

    --rotate cw90
    --rotate ccw90
    --rotate 180

如果本機有桌面環境，可以加 preview：

    --preview

目前遠端終端常沒有 DISPLAY，所以 preview 可能無法使用；不加 preview 也會正常存圖。

## 輸出

預設為獨立暫存，實際路徑會印在終端：

    outputs/tmp/<session_name>_<unique_suffix>/

結束選 `s` 保存、`d` 捨棄、`l` 稍後決定。沒有互動終端時資料會保留待決定。
保存後結果位於 `outputs/live_sessions/<實際名稱>/`，影像放在 `data/captures/`，由 `frames/` 連結存取。
使用 `conda run --no-capture-output` 可直接看到擷取訊息。

內容：

    frames/
      000000.jpg
      000001.jpg
      ...
    capture_manifest.json

`capture_manifest.json` 會記錄：

    source URL
    requested fps
    actual saved fps
    width / height
    saved frame list
    timestamps

## 接到目前離線 Mapping

Capture 完後，可以先用手機 frames 跑離線 LingBot-MAP。
以下的 `phone_test` 必須換成終端顯示的已保存 session 名稱（包含唯一後綴）；
尚未保存時則改用 `outputs/tmp/<實際名稱>/`。低階命令的輸出路徑由使用者指定，不自動清理：

    conda run -n lingbot-map python Integrated_version/experiments/run_lingbot_mapping.py \
      --image-folder outputs/live_sessions/phone_test/frames \
      --model-path models/lingbot-map.pt \
      --output-dir outputs/live_sessions/phone_test/mapping \
      --camera-num-iterations 1 \
      --use-sdpa \
      --output-ply outputs/live_sessions/phone_test/mapping/rebuilt_colored_map.ply \
      --downsample-factor 4

再接 online replay：

    conda run -n lingbot-map python Integrated_version/experiments/run_lingbot_online_replay.py \
      --archive outputs/live_sessions/phone_test/mapping/predictions.npz \
      --output-dir outputs/live_sessions/phone_test/online_replay \
      --write-every 5 \
      --sample-stride 8

產生 3D 俯視 viewer：

    conda run -n lingbot-map python Integrated_version/experiments/export_online_replay_3d_viewer.py \
      --replay-dir outputs/live_sessions/phone_test/online_replay \
      --max-points-per-frame 18000

## 實驗注意

- 手機盡量橫向或固定方向，不要拍一半旋轉。
- 移動速度慢一點，避免 motion blur。
- 前 8 張會影響 bootstrap/floor estimate，開始時先對準地板與前方場景。
- 先收短資料，例如 30 到 100 張，確認可重建後再收長資料。
- PLY 是輸出快照，不是 runtime map。後續真正 online 版本要直接把 frame stream 接到 LingBot session。
