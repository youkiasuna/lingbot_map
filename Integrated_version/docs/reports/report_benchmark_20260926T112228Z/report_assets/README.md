# Benchmark Report Assets

Generated from existing files in `Integrated_version/docs/reports/report_benchmark_20260926T112228Z`.

No benchmark was rerun, and no algorithm/runtime file was changed.

## Files

- `verification_matrix.csv`: evidence table for report claims.
- `verification_explanation.md`: prose explanation of verified / not verified claims.
- `data_inventory.md`: benchmark file inventory, columns, rows, and consistency checks.
- `figure_sources.csv`: source files and fields used by each figure.
- `missing_data_checklist.md`: missing data that must be collected before stronger claims.
- `fig1_architecture.*` through `fig6_orb_status_confidence.*`: report-ready figures.

## Key Guardrails

- ORB results are accepted localization ratio / confidence only, not physical localization accuracy.
- RTSP live performance is `NOT VERIFIED` in this report run.
- Prediction replay uses existing `world_points`; it is not true online RGB monocular 3D reconstruction.
- LingBot persistent percentile values are from only two windows and must be reported with caution.
