"""Safety-oriented state machine for exploration, mapping, and navigation."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class RuntimeMode(str, Enum):
    BOOT = "BOOT"
    MAPPING_ONLY = "MAPPING_ONLY"
    MAP_READY = "MAP_READY"
    NAVIGATING = "NAVIGATING"
    LOCALIZATION_LOST = "LOCALIZATION_LOST"
    RECOVERY_MAPPING = "RECOVERY_MAPPING"

@dataclass
class MappingReadiness:
    keyframe_count: int = 0
    point_count: int = 0
    tracked_ratio: float = 0.0
    navigable: bool = False

@dataclass
class MappingStateMachine:
    min_keyframes: int = 20
    min_points: int = 5000
    min_tracked_ratio: float = 0.70
    mode: RuntimeMode = RuntimeMode.BOOT

    def start(self) -> RuntimeMode:
        self.mode = RuntimeMode.MAPPING_ONLY
        return self.mode

    def update_map_quality(self, quality: MappingReadiness) -> RuntimeMode:
        ready = (quality.keyframe_count >= self.min_keyframes and quality.point_count >= self.min_points and quality.tracked_ratio >= self.min_tracked_ratio and quality.navigable)
        if ready:
            self.mode = RuntimeMode.MAP_READY
        elif self.mode in (RuntimeMode.BOOT, RuntimeMode.MAP_READY, RuntimeMode.NAVIGATING):
            self.mode = RuntimeMode.MAPPING_ONLY
        return self.mode

    def begin_navigation(self) -> RuntimeMode:
        if self.mode != RuntimeMode.MAP_READY:
            raise RuntimeError("navigation requires a ready live map")
        self.mode = RuntimeMode.NAVIGATING
        return self.mode

    def localization_lost(self) -> RuntimeMode:
        self.mode = RuntimeMode.LOCALIZATION_LOST
        return self.mode

    def begin_recovery(self) -> RuntimeMode:
        self.mode = RuntimeMode.RECOVERY_MAPPING
        return self.mode

    def recover_map(self, quality: MappingReadiness) -> RuntimeMode:
        self.mode = RuntimeMode.MAPPING_ONLY
        return self.update_map_quality(quality)
