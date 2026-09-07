# Visual Navigation Progress Plan

## Current Position

The project can already generate an occupancy map from a point cloud, choose a
goal in a browser, create an A* route, and expose navigation state. The pose
provider is still a mock, and no autonomous command is sent to the ESP32.

| Area | Status | Evidence |
| --- | --- | --- |
| Point cloud to 2D occupancy map | Complete | `map_localization_test/build_topdown_map.py` |
| Occupancy-map goal selection | Complete | `map_localization_test/web/` |
| A* path planning | Complete | `map_localization_test/grid_navigation.py` |
| Runtime pose/path contracts | Complete for test use | JSON files and web API |
| Visual relocalization | Not started | Mock pose is still in use |
| Path following | Not started | No Pure Pursuit controller |
| Autonomous ESP32 transport | Not started | Manual controller only |
| Simulation and hardware acceptance | Not started | No repeatable test suite |

## Milestones

### M0. Lock Interfaces and Vehicle Parameters

Purpose: remove ambiguity before connecting perception to motors.

- Define JSON schemas for pose, localization confidence, route, controller
  command, and navigation state.
- Record camera calibration, camera-to-robot transform, wheel base, wheel
  radius, speed limits, and stopping distance in versioned configuration.
- Define map axes, metres, yaw direction, and timestamp conventions.
- Define `LOCALIZATION_LOST`, `PATH_BLOCKED`, `CONTROLLER_TIMEOUT`, and
  `ESP32_UNREACHABLE` states.

Done when: every module can exchange data without implicit units or coordinate
assumptions.

### M1. Reproducible Map Build

Purpose: produce a navigation map that matches the real driving area.

- Run LingBot-Map on a recorded indoor scan and keep map artifacts outside Git.
- Convert the point cloud using recorded floor range, obstacle height, map
  resolution, and obstacle inflation.
- Verify walls, gaps, and traversable corridors in the web UI.
- Export a small anonymous sample map only when a regression test needs one.

Done when: repeated conversion produces the same map and manual goals create
collision-free routes in representative indoor areas.

### M2. Visual Relocalization MVP

Purpose: replace the mock pose with a camera-derived pose in the saved map.

- Choose LingBot keyframes, 3D landmarks, or both as the reference data.
- Extract ORB features from live images and reference keyframes.
- Match features, reject outliers with RANSAC, and estimate camera pose with
  PnP when enough 2D-3D correspondences exist.
- Transform camera pose into robot-base pose using calibrated extrinsics.
- Publish pose, timestamp, inlier count, reprojection error, and confidence.

Done when: the robot remains localized while moving slowly in a known area and
enters `LOCALIZATION_LOST` rather than publishing an untrusted pose.

### M3. Planner Integration and Replanning

Purpose: turn live pose and a selected goal into a usable route.

- Use validated visual pose as the A* start point.
- Reject goals in occupied, inflated, or unknown cells.
- Add goal tolerance and route completion criteria.
- Replan after meaningful pose drift, map/path invalidation, or user goal
  change; rate-limit replanning to avoid controller oscillation.
- Display pose confidence, goal, route, and planner errors in the web UI.

Done when: free goals reliably create routes and invalid goals produce a clear
non-driving error state.

### M4. Pure Pursuit Controller in Simulation

Purpose: verify motion logic before exposing motors.

- Implement lookahead selection, curvature calculation, and speed reduction
  for sharp turns.
- Convert linear/angular velocity to left/right wheel velocity using wheelbase.
- Add goal tolerance, velocity limits, acceleration limits, and timeout.
- Test replayed pose sequences and synthetic paths, including corners, lost
  localization, and final approach.

Done when: simulated runs reach representative goals with bounded commands and
without crossing occupied cells.

### M5. ESP32 Navigation Adapter and Safety Layer

Purpose: make command delivery explicit, bounded, and easy to stop.

- Define the ESP32 wheel-speed protocol and acknowledgment behavior.
- Add connection timeout, retry policy, and zero-speed commands on failures.
- Keep manual stop independent from the autonomous loop.
- Require recent high-confidence pose, current route, and operator start action
  before enabling motor output.
- Add an ESP32 dead-man timeout so missing commands stop the motors.

Done when: disconnecting network, camera, or controller causes a stop within
the configured safety limit.

### M6. Closed-Loop Indoor Validation

Purpose: tune the complete system under controlled conditions.

- Start at low speed with open floor space and short paths.
- Measure final-position error, tracking error, localization dropout rate,
  stopping distance, and route completion rate.
- Tune inflation, resolution, lookahead distance, speed caps, and confidence
  thresholds one parameter group at a time.
- Expand to tighter corridors and longer paths only after repeatable success.

Done when: agreed indoor routes complete repeatedly and localization loss stops
the robot safely with usable diagnostic logs.

### M7. Operational UI and Documentation

Purpose: make the system usable without a developer in the loop.

- Add map, pose, controller, and connection freshness status.
- Show autonomous state, safety reason, route length, and goal result.
- Provide start, stop, emergency-stop, and map reload actions.
- Document scanning, map build, calibration, pre-drive checks, and recovery.

Done when: an operator can prepare a map, select a goal, perform a safe test,
and understand why the system refuses to move.

## Recommended Execution Order

`M0 -> M1 -> M2 -> M3 -> M4 -> M5 -> M6 -> M7`

M2 and M4 are the critical development streams. Do not enable M5 motor output
until M2 reports reliable confidence and M4 has passed replay tests.

## First Implementation Slice

1. Add `config/vehicle.json` and `config/camera.json` with explicit units.
2. Add a Pure Pursuit module that reads `current_pose.json` and
   `planned_path.json` and writes a controller-command JSON file.
3. Add offline tests with fixed poses and paths.
4. Keep the ESP32 adapter disabled until those tests pass.
