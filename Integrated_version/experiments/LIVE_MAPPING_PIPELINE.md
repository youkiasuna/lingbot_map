# Live mapping pipeline

This demo keeps the phone camera running while mapping runs in a background
worker. The current LingBot-MAP model is still batch-oriented, so each update
processes all frames captured up to that point. Capture is never blocked by the
GPU job; this is the correct integration boundary for the first hardware test.

## Start

Run one command in the `lingbot-map` environment:

```bash
cd /media/ee303/1tb/lingbot_map

conda run --no-capture-output -n lingbot-map python -B Integrated_version/experiments/run_live_mapping_pipeline.py \
  --url http://192.168.50.98:8080/video \
  --session-name ipwebcam \
  --fps 5 \
  --batch-frames 30 \
  --process-every 30 \
  --max-frames 0 \
  --camera-num-iterations 1 \
  --use-sdpa
```

Press `Ctrl+C` to stop. The camera capture and the background processor then
shut down together.

## Outputs

Each new session is temporary and has a unique suffix. The exact path is printed:

`outputs/tmp/ipwebcam_<unique_suffix>/`

- `frames/`: captured JPEG frames
- `pipeline_status.json`: live state and frame counters
- `pipeline.log`: mapping and replay logs
- `mapping/latest/`: latest `predictions.npz` and colored PLY
- `online_replay/latest/`: latest map, snapshots, and 3D viewer

Start a static server in another terminal:

```bash
cd /media/ee303/1tb/lingbot_map
python3 -m http.server 18116 --bind 127.0.0.1
```

Open the viewer using the actual temporary session name:

`http://127.0.0.1:18116/outputs/tmp/ipwebcam_<unique_suffix>/online_replay/latest/online_replay_3d_top_viewer.html`

After processing stops, choose `s` (save), `d` (discard), or `l` (decide later).
Without an interactive terminal the data stays pending; nothing is automatically deleted.
Saving moves the results into `outputs/live_sessions/` and frames into `data/captures/`,
with a relative `frames/` link retained in the result package. The viewer URL then
uses `outputs/live_sessions/<actual_session_name>/` instead of `outputs/tmp/`.
The checkpoint remains at `models/lingbot-map.pt` and is never a temporary result.

Refresh the browser after each completed update. The next iteration can replace
the batch worker with a persistent model object without changing capture,
status, or web output paths.
