# Shared data schemas

`core.py` defines the first version of the data contracts shared by the
research and runtime pipelines.

The records are additive only at this stage. Existing producers and output
files are not changed yet, so current experiments remain reproducible.

## Records

- `FrameRecord`: camera frame identity, source, and timestamp.
- `PoseRecord`: position, orientation, confidence, and coordinate frame.
- `PointCloudRecord`: metadata for an NPZ/PLY point-cloud snapshot.
- `LocalizationResult`: query localization result and quality metrics.
- `NavigationCommand`: safe vehicle/simulation velocity command.
- `MapStatusRecord`: stable live-session status and viewer file references.

`NavigationCommand.from_twist()` adapts the existing planner command shape
without importing the planner or hardware modules into the schema layer.

All records expose `to_dict()` and include `schema_version: 1`. Point-cloud
arrays remain in binary files; the record stores their metadata and path.

## Coordinate rule

`coordinate_frame` is required in pose and point-cloud records. The value is
descriptive metadata, not an implicit conversion. Current reconstruction
experiments use the scene-specific reconstruction convention (`-Y` vertical,
navigation projected on `X/Z`), which must be recorded by future producers.
