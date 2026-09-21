"""JSON publisher consumed by a live 3D viewer."""
from __future__ import annotations
from runtime.live_map_manager import LiveMapManager

class LiveViewerState:
    """Publish pose, path, and status without reloading the complete point cloud."""

    def __init__(self, map_manager: LiveMapManager) -> None:
        self.map_manager = map_manager

    def update(self, *, position_xyz: list[float] | None, yaw_deg: float | None, confidence: float, localization_status: str, mode: str, path_xz: list[tuple[float, float]] | None = None) -> None:
        self.map_manager.publish_pose(position_xyz, yaw_deg, confidence=confidence, status=localization_status)
        if path_xz is not None:
            self.map_manager.publish_path(path_xz)
        self.map_manager.publish_status(mode=mode, localization_status=localization_status, viewer_pointcloud="live_points.json" if self.map_manager.publish_json_points else "live_points.npz", viewer_pose="live_pose.json", viewer_path="live_path.json")
