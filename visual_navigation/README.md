# Pure Visual Navigation Plan

This directory is the integration workspace for camera-only mapping,
localization, waypoint planning, and robot navigation.

## Scope

- Environment sensing: monocular RGB camera only.
- Map source: LingBot-Map point cloud and camera poses.
- Planning map: 2D occupancy grid generated from the point cloud.
- Navigation input: a user-selected goal on the web map.
- Motion output: differential-drive wheel commands sent to the ESP32.

The camera is the environmental sensor. Wheel control remains separate from
visual perception and must always support a hardware stop command.

## Existing Building Blocks

| Capability | Current location | Status |
| --- | --- | --- |
| Point cloud to occupancy map | `map_localization_test/build_topdown_map.py` | Available |
| Pose JSON contract | `map_localization_test/mock_pose_tracker.py` | Mock provider available |
| A* path planner | `map_localization_test/grid_navigation.py` | Available |
| Goal selection and map UI | `map_localization_test/web_server.py` and `web/` | Available |
| ESP32 manual controller | `car/car/web_controller.py` | Available |
| Visual relocalization | This directory | To implement |
| Path following and motor adapter | This directory | To implement |

## Runtime Data Contract

All coordinates use metres in the map frame. Positive yaw is counterclockwise.

```text
camera / visual localizer
  -> current_pose.json { x_m, y_m, yaw_rad, timestamp }
  -> A* planner
  -> planned_path.json { waypoints: [{ x_m, y_m }] }
  -> Pure Pursuit controller
  -> wheel command adapter
  -> ESP32
```

`current_pose.json`, `planned_path.json`, and `navigation_state.json` are
runtime files and remain ignored by Git.

## Implementation Sequence

1. Define the visual-localization input and output contract, including pose
   confidence and a lost-localization state.
2. Replace the mock pose provider with feature matching and PnP/RANSAC against
   stored keyframes or map landmarks.
3. Add a Pure Pursuit controller that consumes the planned path and publishes
   linear/angular velocity commands.
4. Add an ESP32 adapter that converts velocity to left/right wheel commands,
   with a command timeout and explicit stop behavior.
5. Connect controller state to the web API: `GOAL_SELECTED`, `NAVIGATING`,
   `LOCALIZATION_LOST`, `GOAL_REACHED`, and `STOP`.
6. Validate in simulation before enabling motor output, then tune speed,
   lookahead distance, obstacle inflation, and stopping distance on hardware.

## Safety Gates

- Never start autonomous motor output when pose confidence is below threshold.
- Stop when localization is stale, the planned path is missing, or the command
  link to the ESP32 fails.
- Treat unknown occupancy cells as blocked for normal navigation.
- Keep manual stop available independently of the navigation loop.

## Proposed Layout

```text
visual_navigation/
  README.md
  localization/       # Visual relocalization provider
  control/            # Pure Pursuit and differential-drive logic
  hardware/           # ESP32 command transport and safety timeout
  config/             # Camera, vehicle, and controller parameters
  tests/              # Offline pose, path, and controller tests
```
