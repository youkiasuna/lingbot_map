# RTSP mapping-only workflow

This workflow does not run ORB localization, A*, Pure Pursuit, or ESP32 control.

RTSP -> persistent LingBot-MAP -> local points -> voxel fusion -> live_map outputs

Run continuously:

    PYTHONPATH=Integrated_version python Integrated_version/runtime/live_pointcloud_runtime.py \
      --url rtsp://PHONE_IP:8554/live \
      --model-path models/lingbot-map.pt \
      --lingbot-root lingbot-map-main \
      --live-map-dir outputs/runtime/online_navigation \
      --window-size 10 \
      --process-every 10 \
      --fps 5 \
      --max-windows 0 \
      --max-frames 0

The runtime keeps the camera loop alive, retries failed RTSP reads, limits
submitted frames with --fps, and writes live_points.npz, live_map.json, and
live_status.json. Mapping failures are reported in live_status.json.

--mapping-dir is intentionally not required in this mode. The algorithm
remains the existing LingBot-MAP inference plus IncrementalVoxelMap fusion.
