# Verification Explanation

All items here are derived from files already present in `Integrated_version/docs/reports/report_benchmark_20260926T112228Z`. No benchmark was rerun while preparing these assets.

## What Is Actually Verified

- Unit tests: `unit_test_output.txt` records `Ran 36 tests` and `OK`.
- Prediction replay fusion: `pipeline_summary.csv` and `map_growth.csv` verify that the existing `predictions.npz` data path produced 34 map updates and final voxel count 33,947.
- Persistent LingBot worker: `latency_by_stage.csv` verifies session-level model load and per-window timing separation. Only two windows are available, so percentile statistics must be reported with caution.
- ORB same-scene replay: `orb_localization_summary.json` verifies 30/30 localized frames for `data/videos/20260818.mp4`, with mean confidence 0.9864.

## What Is Not Verified

- RTSP live performance in this report run: `rtsp_summary.json` records `connection refused`.
- Update-aligned GPU memory trend: only separate samples exist; there is no per-map-update GPU memory series.
- Physical position/yaw error: no external ground truth exists in the benchmark artifacts.
- True streaming monocular reconstruction: prediction replay uses existing `world_points`, and LingBot tests are windowed inference, not a complete streaming SLAM claim.

## Reporting Language Guardrails

Use "accepted localization ratio" for ORB replay, not "localization accuracy". Use `NOT AVAILABLE` for position/yaw error without physical ground truth. Mark every RTSP/front-end/live-queue metric from this benchmark as `NOT VERIFIED` unless a later run produces raw evidence.
