# Fixed Report Figures

Generated at 20260927T055424Z from existing benchmark CSV/JSON files only. No benchmark was rerun, no interpolation was used, and no algorithm/runtime file was modified.

## Corrections

1. Figure 1 separates target architecture from this benchmark's evidence scope.
2. Figure 2 uses split subplots instead of a dual Y-axis.
3. Figure 3 uses only the `prediction_long300` row and explicitly labels 43 source frames / 34 updates / mean 354.894 ms.
4. Figure 4 uses grouped bars and separate total bars because stage fields must not be shown as a mutually exclusive stack.
5. Figure 5 avoids title/axis overlap and does not draw GPU memory as a time-series.
6. Figure 6 splits confidence from status and uses frame-level records only because they exist in `orb_localization_summary.json`.

See `fixed_figure_sources.csv` for exact source fields.
