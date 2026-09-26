# Benchmark Report: report_benchmark_20260926T112228Z

## Environment

- hostname: ee303-3090
- python: 3.10.20
- torch: 2.8.0+cu128
- cuda: True
- gpu: NVIDIA GeForce RTX 3090
- opencv: 5.0.0
- numpy: 2.2.6
- git_branch: codex/schema-consolidation-latest
- git_commit: ba8ed03adcfe9cfe68401a0d48320f05ce7e9fae
- git_status_short: M Integrated_version/runtime/lingbot_map_session.py
 M Integrated_version/runtime/live_pointcloud_runtime.py
 M Integrated_version/tests/test_rgb_pointcloud.py
- traceability_note: Results were collected from base commit `ba8ed03` with local runtime fixes; `local_changes.patch` records the exact code delta used for the benchmark.

## Basic Validation

- compileall: PASS
- unit_tests: 36 tests OK
- failed_tests: []
- cli_help: PASS for live_pointcloud_runtime, run_live_mapping_replay, online_mapping_navigation

## Pipeline Summary

| pipeline | backend | updates | latency field | mean ms | p50 ms | p95 ms | peak RSS MB | peak GPU MB | final voxels | status |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| prediction_json | prediction | 0 | N/A | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT SUPPORTED BY CURRENT CLI |
| prediction_npz | prediction | 34 | latency_ms from replay_summary records | 361.842 | 366.035 | 381.951 | 829.16 | NOT SAMPLED | 33947 | OK |
| prediction_long300 | prediction | 34 | latency_ms from replay_summary records | 354.894 | 356.565 | 379.322 | 828.828 | 631.0 | 33947 | OK |
| lingbot_persistent_archive | lingbot | 2 | backend_timings_ms.backend_total | 4017.81 | 4017.81 | 4936.321 | 5305.5 | 9810.0 | 8957 | OK; P95 uses nearest-rank over only 2 windows, report with caution |
| lingbot_persistent_fast | lingbot | 2 | backend_timings_ms.backend_total | 2027.343 | 2027.343 | 2955.299 | 5291.211 | 9808.0 | 8957 | OK; P95 uses nearest-rank over only 2 windows, report with caution |

## LingBot Persistent Timing Clarification

All LingBot per-window latency values in this report use `backend_timings_ms.backend_total`. `session_timings_ms.model_load_ms` is reported once at session level and is not repeatedly added to each window. `wrapper_backend_latency_ms` is preserved in `latency_by_stage.csv` but not used for the report table.
- archive session_model_load_ms: 11776.987
  - window 0-9: backend_total_ms=4936.321, session_total_ms=4935.358, wrapper_backend_latency_ms=4991.309, archive_write_ms=2010.634
  - window 10-19: backend_total_ms=3099.299, session_total_ms=3098.371, wrapper_backend_latency_ms=3154.743, archive_write_ms=2005.123
- fast session_model_load_ms: 11820.182
  - window 0-9: backend_total_ms=2955.299, session_total_ms=2954.67, wrapper_backend_latency_ms=3009.181, archive_write_ms=0.0
  - window 10-19: backend_total_ms=1099.387, session_total_ms=1098.61, wrapper_backend_latency_ms=1152.256, archive_write_ms=0.0
Because each persistent benchmark has only two windows, p95 is computed with nearest-rank and should be interpreted cautiously. The report should emphasize raw per-window timings.

## RTSP

RTSP mapping for this report run is NOT VERIFIED because the smoke test failed with connection refused. Old RTSP results were not reused.

## ORB Localization

- same-scene reference: localized, confidence=1.0, inliers=300
- video replay accepted localization ratio: 1.0 (30/30)
- mean confidence: 0.9864
- physical positioning accuracy: NOT AVAILABLE, no external ground truth

## Data Growth and Memory

- rss_memory_trend: slightly_increasing
- rss_start_mb: 808.203
- rss_end_mb: 828.828
- gpu_memory_trend: NOT VERIFIED as update-aligned series; sampled separately in prediction_long300_gpu.csv
- voxel_trend: increasing
- latency_trend: not_monotonic_or_short_series
- latency_start_ms: 329.489
- latency_end_ms: 382.735
- output_size_trend: increasing
- queue_accumulation: NOT VERIFIED: prediction replay has no RTSP queue
- obvious_memory_leak: NOT VERIFIED: only 34 updates available from 43-frame package
- source_data_limit: predictions.npz has 43 frames; max_frames=300 produced 34 windows only; max_frames=600 not run

## Report Conclusions

Performance: In the fixed 20260818 prediction package, the system completed 34 incremental map updates with mean update latency 361.842 ms, final voxel count 33,947, and peak RSS about 829 MB. With a persistent LingBot-MAP worker, model loading is concentrated in session initialization at about 11.8 s and is not repeated per window. Using the fast path with no per-window archive write reduced the second window backend_total_ms from 3099.299 ms in archive mode to 1099.387 ms.
Localization: In the same 20260818 scene, ORB + PnP/RANSAC relocalized all first 30 frames of the replay video, giving an accepted localization ratio of 1.0 and mean confidence 0.9864. This is an acceptance-rate result, not physical positioning accuracy.
Limitations: RTSP was NOT VERIFIED in this report run due connection refused. Prediction replay and window-based LingBot inference are not full real-time SLAM. Memory leak assessment remains NOT VERIFIED because the prediction package contains only 43 frames. Physical position/yaw accuracy is NOT AVAILABLE without external ground truth.