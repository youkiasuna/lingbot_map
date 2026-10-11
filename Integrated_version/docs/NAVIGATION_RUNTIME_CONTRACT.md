# Runtime Data Contract

All navigation coordinates use the map frame in metres. `yaw_deg` follows the
existing map UI convention: zero points toward positive X and positive angles
turn counter-clockwise. Unix timestamps use seconds.

## `current_pose.json`

Written by the mock tracker during development and by visual relocalization in
operation.

```json
{
  "schema_version": 1,
  "x_m": 1.25,
  "y_m": 0.8,
  "yaw_deg": 90.0,
  "timestamp_unix": 1760000000.0,
  "source": "visual_localizer",
  "confidence": 0.93
}
```

Required fields: `x_m`, `y_m`, and `yaw_deg`.

Before motor output is enabled, `timestamp_unix` and `confidence` are also
required. A stale pose or confidence below `vehicle.json.safety` must produce
`LOCALIZATION_LOST` and a stop command.

## `planned_path.json`

Written by the A* planner. The current implementation already emits the
following fields.

```json
{
  "status": "planned",
  "start": { "x_m": 1.25, "y_m": 0.8, "pixel": [12, 20] },
  "goal": { "x_m": 2.4, "y_m": 1.1, "pixel": [35, 16] },
  "waypoints": [{ "x_m": 1.25, "y_m": 0.8 }],
  "path_length_m": 1.2,
  "planned_at_unix": 1760000000.0
}
```

The controller consumes `waypoints`, `goal`, and `planned_at_unix`. It must not
drive when a route is absent, malformed, or older than the configured policy.

## `controller_command.json`

This file will be introduced by the Pure Pursuit controller. It is a local
runtime file and must not be committed.

```json
{
  "schema_version": 1,
  "timestamp_unix": 1760000000.0,
  "linear_speed_mps": 0.1,
  "angular_speed_radps": 0.0,
  "left_wheel_speed_mps": 0.1,
  "right_wheel_speed_mps": 0.1,
  "state": "TRACKING"
}
```

## `navigation_state.json`

Permitted states are `STOP`, `GOAL_SELECTED`, `NAVIGATING`,
`LOCALIZATION_LOST`, `PATH_BLOCKED`, `GOAL_REACHED`, `CONTROLLER_TIMEOUT`, and
`ESP32_UNREACHABLE`. Every state update includes `updated_at_unix`; all states
other than `GOAL_SELECTED` and `NAVIGATING` include a human-readable `reason`.
