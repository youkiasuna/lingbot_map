# Figure Fix V2

Generated at 20260927T060042Z from existing benchmark CSV/JSON files only.

No benchmark was rerun, no data was interpolated or invented, and no algorithm/runtime file was modified.

Corrections in this version:

1. Figure 1A uses two clear branches: mapping branch and ORB localization/navigation branch. The reference map points into ORB localization. PoseGate/Navigation does not point to voxel fusion.
2. Figure 2-6 increase bottom margins, subplot spacing, and source-note separation from X-axis labels/ticks.
3. Figure 4 keeps grouped stage bars plus separate total latency bars; fast-path archive_write_ms is explicitly labeled 0 ms.

See `figure_sources_v2.csv` for exact source files and fields.
