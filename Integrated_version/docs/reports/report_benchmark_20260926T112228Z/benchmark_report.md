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

## Basic Validation

- compileall: PASS
- unit_tests: 36 tests OK
- failed_tests: []
- cli_help: PASS for live_pointcloud_runtime, run_live_mapping_replay, online_mapping_navigation

## Pipeline Summary

| pipeline | backend | updates | mean_latency_ms | p50_latency_ms | p95_latency_ms | peak_rss_mb | peak_gpu_memory_mb | final_voxel_count | final_output_bytes | status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| prediction_json | prediction | 0 | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT SUPPORTED BY CURRENT CLI |
| prediction_npz | prediction | 34 | 361.842 | 366.035 | 381.951 | 829.16 | None | 33947 | 374344 | OK |
| prediction_long300 | prediction | 34 | 354.894 | 356.565 | 379.322 | 828.828 | 631.0 | 33947 | 374345 | OK |
| lingbot_persistent_archive | lingbot | 2 | 336.12 | 336.12 | 333.1 | 5305.5 | 9810.0 | 8957 | 101177 | OK |
| lingbot_persistent_fast | lingbot | 2 | 327.255 | 327.255 | 323.763 | 5291.211 | 9808.0 | 8957 | 101178 | OK |

## RTSP

RTSP mapping for this report run is NOT VERIFIED because the smoke test failed with connection refused. Old RTSP results were not reused.

## ORB Localization

- same-scene reference: localized, confidence=1.0, inliers=300
- video replay accepted localization ratio: 1.0 (30/30)
- physical positioning accuracy: NOT AVAILABLE, no external ground truth

## Report Conclusions

Performance: On commit ba8ed03 plus local uncommitted runtime fixes, prediction replay over the 20260818 package produced 34 updates with mean fusion/output latency 361.842 ms and final voxel count 33947. Persistent LingBot fast path removed archive_write from the window hot path and reduced window-2 backend latency from 3154.743 ms to 1152.256 ms compared with archive mode.
Localization: ORB relocalization is verified on same-scene 20260818 inputs: preprocessed/000000.png localized with confidence 1.0 and 300 inliers; the first 30 frames of 20260818.mp4 had accepted localization ratio 1.0. This is an acceptance ratio, not physical accuracy.
Limitations: RTSP was NOT VERIFIED in this report run due connection refused; prediction replay and windowed LingBot inference are not full real-time SLAM; physical position/yaw accuracy is NOT AVAILABLE without ground truth; memory leak assessment is NOT VERIFIED due short 43-frame source package.