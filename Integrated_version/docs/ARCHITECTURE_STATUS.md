# Architecture Status and Preservation Rules

This document records the current role of the project directories before any
cleanup. Classification does not delete or move files.

## Active integration path

The maintained integration path is:

```text
Integrated_version/schemas
    -> Integrated_version/runtime
    -> Integrated_version/web
```

Current active responsibilities:

| Area | Location | Role |
| --- | --- | --- |
| Shared contracts | `Integrated_version/schemas/` | Versioned frame, pose, map, localization, window, and command records |
| Mapping runtime | `Integrated_version/runtime/` | Queue, LingBot backend, window processing, map publication |
| Research localization | `Integrated_version/experiments/` | ORB/PnP and reproducible offline experiments |
| Web API/viewer | `Integrated_version/web/` | Live map API and monitoring dashboard |
| Navigation planner | `Integrated_version/planner/` | 2D map planning and pure-pursuit support |
| Tests | `Integrated_version/tests/` | Unit and integration-oriented smoke tests |

## Research assets that must be preserved

The following are research inputs or outputs, not disposable runtime cache:

- formal mapping/query split manifests;
- `predictions.npz` and matching preprocessed images;
- reconstructed PLY files;
- experiment summaries and benchmark reports;
- coordinate convention metadata;
- reproducibility run manifests.

They must not be overwritten by a new run unless the user explicitly selects an
output directory and confirms replacement.

## Alternative and prototype paths

| Location | Classification | Preservation rule |
| --- | --- | --- |
| `Tony's project/` | Streaming prototype/reference | Keep unchanged; use for comparison and ideas |
| `car/` | Hardware/application prototype | Keep separate from research core |
| `map_localization_test/` | Legacy/standalone localization demo | Do not import into the active path without review |
| `visual_navigation/` | Planning prototype/reference | Reuse algorithms only after interface review |
| `lingbot-map-main/` | Upstream/vendor model implementation | Do not modify unless required by the backend contract |

These directories may later be moved under an archive area, but only after a
dependency scan, result inventory, replacement plan, and explicit approval.

## Canonical data flow

The intended maintained flow is:

```text
FrameRecord
  -> MappingWindowRecord
  -> PointCloudRecord
  -> LiveMapManager
  -> web API
  -> viewer
```

Optional color path:
  
```text
LingBot-MAP session (--extract-rgb)
  -> colors_rgb aligned with points_xyz
  -> LiveMapManager
  -> live_points.npz (points_xyz + colors_rgb)
```

The color path is disabled by default. Geometry-only live mapping remains the
compatibility baseline. RGB data is valid only when the point and color arrays
have identical lengths and use the declared `rgb_uint8` format. The live map
API exposes the aligned arrays as `points_xyz` and `colors_rgb`; the web
viewer uses RGB when available and keeps the height-based fallback otherwise.

The web viewer also polls `/api/live/pose`. A red pose marker is shown
only when `live_pose.json.position_xyz` contains three finite coordinates. A
missing, rejected, or stale pose does not create a marker.

The RTSP live mapping runtime now accepts an optional
`--localization-mapping-dir`. When supplied, the same captured frames are
sent to the existing ORB relocalizer and only accepted poses are written as
valid coordinates in `live_pose.json`; rejected results publish no position.
Without this option, the runtime remains mapping-only.

ORB localization uses a bounded latest-frame worker. If ORB is
slower than the RTSP input, stale pending frames are dropped and the queue
does not grow without limit. Runtime status records
`localization_processed_frames` and `localization_dropped_frames`.

Localization and navigation are downstream consumers:

```text
LocalizationResult
  -> PoseRecord
  -> NavigationCommand
```

The records are additive compatibility layers at present. Existing legacy JSON
fields remain available until all consumers are migrated and tested.

## Cleanup policy

Before removing or moving any file:

1. Search imports and command references.
2. Identify research outputs that depend on it.
3. Mark the replacement entry point.
4. Add or update a smoke test.
5. Preserve the old path for one migration cycle.
6. Ask for confirmation before destructive cleanup.

This policy is intentionally conservative so research results remain
reproducible.
