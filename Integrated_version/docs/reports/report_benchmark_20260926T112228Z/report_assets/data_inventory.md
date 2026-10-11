# Report Data Inventory

This inventory was generated from existing benchmark artifacts only. No benchmark was rerun.

## Git State During Asset Generation

- Current branch/status: `## codex/schema-consolidation-latest...origin/codex/schema-consolidation-latest
?? Integrated_version/docs/reports/report_benchmark_20260926T112228Z/report_assets/`

- Current HEAD: `9f6b09cc3957d34de586c28cf405c9fb37847146`

- Benchmark-recorded base commit: `ba8ed03adcfe9cfe68401a0d48320f05ce7e9fae`

- Benchmark traceability note: `environment.json` records local runtime fixes at benchmark time; `local_changes.patch` preserves those changes.

## Files

| File | Type | Rows/Kind | Columns / Keys | Size |
|---|---:|---:|---|---:|
| `benchmark_report.md` | .md |  |  | 5192 |
| `environment.json` | .json | object | hostname, pwd, python, python_executable, torch, cuda, gpu, opencv, numpy, git_status_short, git_branch, git_commit, git_log_oneline_5, nvidia_smi_query, nvidia_smi_full | 3179 |
| `frame_processing.png` | .png |  |  | 27658 |
| `latency_breakdown.png` | .png |  |  | 34654 |
| `latency_by_stage.csv` | .csv | 4 | pipeline, window, image_prepare_ms, session_model_load_ms, inference_ms, archive_write_ms, point_extract_ms, fusion_output_latency_ms, session_total_ms, backend_total_ms, wrapper_backend_latency_ms | 608 |
| `latency_comparison.png` | .png |  |  | 28193 |
| `local_changes.patch` | .patch |  |  | 3770 |
| `localization_confidence.png` | .png |  |  | 34517 |
| `map_growth.csv` | .csv | 34 | update_index, timestamp, map_version, processed_frames, input_points, fused_points, voxel_count, output_bytes, latency_ms, rss_mb, gpu_memory_mb | 3204 |
| `map_growth.png` | .png |  |  | 23640 |
| `memory_growth.csv` | .csv | 34 | update_index, map_version, rss_mb, latency_ms, voxel_count, output_bytes | 1270 |
| `memory_growth.png` | .png |  |  | 19023 |
| `memory_trend_summary.json` | .json | object | rss_memory_trend, rss_start_mb, rss_end_mb, gpu_memory_trend, voxel_trend, latency_trend, latency_start_ms, latency_end_ms, output_size_trend, queue_accumulation, obvious_memory_leak, source_data_limit | 680 |
| `orb_localization_summary.json` | .json | object | reference_image, video_replay, physical_positioning_accuracy | 10151 |
| `pipeline_summary.csv` | .csv | 5 | pipeline, backend, updates, mean_latency_ms, p50_latency_ms, p95_latency_ms, peak_rss_mb, peak_gpu_memory_mb, final_voxel_count, final_output_bytes, status, latency_field, notes | 1315 |
| `pipeline_summary.json` | .json | 5 | list records | 2603 |
| `rtsp_summary.json` | .json | object | rtsp_url, camera_connection, frame_read, frame_shape, mapping, rgb_point_cloud, localization, frontend_api, esp32, reader_error | 406 |
| `test_commands.txt` | .txt |  |  | 2538 |
| `unit_test_output.txt` | .txt |  |  | 3991 |

## Consistency Checks

| Check | Result | Source |
|---|---:|---|
| prediction_long300 mean latency | PASS | `pipeline_summary.csv` |
| prediction_long300 final voxel | PASS | `pipeline_summary.csv` |
| LingBot fast latency field | PASS | `pipeline_summary.csv / latency_by_stage.csv` |
| RTSP connection refused | PASS | `rtsp_summary.json` |
| ORB accepted ratio warning | PASS | `orb_localization_summary.json` |
| local patch disclosed | PASS | `environment.json / local_changes.patch` |

## Existing Figure Files And Source Data

| Existing figure | Source | Fields |
|---|---|---|
| `frame_processing.png` | `orb_localization_summary.json` | video_replay.records latency/status |
| `latency_breakdown.png` | `latency_by_stage.csv` | stage timing columns |
| `latency_comparison.png` | `pipeline_summary.csv` | mean/p50/p95 latency fields |
| `localization_confidence.png` | `orb_localization_summary.json` | video_replay.records confidence/status |
| `map_growth.png` | `map_growth.csv` | map_version/voxel_count/output_bytes/latency_ms |
| `memory_growth.png` | `memory_growth.csv` | rss_mb/output_bytes/latency_ms |
