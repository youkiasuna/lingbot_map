#!/usr/bin/env python3
"""Validate visual-navigation configuration before enabling a controller."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when a configuration cannot safely be used."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing configuration: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"Configuration root must be an object: {path}")
    return payload


def require_mapping(payload: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{context}.{key} must be an object")
    return value


def require_number(value: Any, name: str, unresolved: list[str]) -> None:
    if value is None:
        unresolved.append(name)
    elif not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"{name} must be a number or null")


def validate_camera(payload: dict[str, Any]) -> list[str]:
    if payload.get("schema_version") != 1:
        raise ConfigError("camera.schema_version must be 1")
    if payload.get("calibration_status") not in {"UNSET", "CALIBRATED"}:
        raise ConfigError("camera.calibration_status must be UNSET or CALIBRATED")

    unresolved: list[str] = []
    image = require_mapping(payload, "image", "camera")
    intrinsics = require_mapping(payload, "intrinsics_px", "camera")
    transform = require_mapping(payload, "camera_to_base", "camera")
    translation = require_mapping(transform, "translation_m", "camera.camera_to_base")
    rotation = require_mapping(transform, "rotation_rpy_rad", "camera.camera_to_base")

    for key in ("width_px", "height_px"):
        require_number(image.get(key), f"camera.image.{key}", unresolved)
    for key in ("fx", "fy", "cx", "cy"):
        require_number(intrinsics.get(key), f"camera.intrinsics_px.{key}", unresolved)
    for key in ("x", "y", "z"):
        require_number(translation.get(key), f"camera.camera_to_base.translation_m.{key}", unresolved)
    for key in ("roll", "pitch", "yaw"):
        require_number(rotation.get(key), f"camera.camera_to_base.rotation_rpy_rad.{key}", unresolved)
    return unresolved


def validate_vehicle(payload: dict[str, Any]) -> list[str]:
    if payload.get("schema_version") != 1:
        raise ConfigError("vehicle.schema_version must be 1")
    if payload.get("calibration_status") not in {"UNSET", "CALIBRATED"}:
        raise ConfigError("vehicle.calibration_status must be UNSET or CALIBRATED")
    if payload.get("vehicle_type") != "differential_drive":
        raise ConfigError("vehicle.vehicle_type must be differential_drive")

    unresolved: list[str] = []
    require_number(payload.get("wheel_radius_m"), "vehicle.wheel_radius_m", unresolved)
    require_number(payload.get("wheel_base_m"), "vehicle.wheel_base_m", unresolved)
    limits = require_mapping(payload, "limits", "vehicle")
    safety = require_mapping(payload, "safety", "vehicle")
    for key in ("max_linear_speed_mps", "max_angular_speed_radps", "max_linear_accel_mps2", "goal_tolerance_m", "command_timeout_s"):
        require_number(limits.get(key), f"vehicle.limits.{key}", unresolved)
    require_number(safety.get("minimum_pose_confidence"), "vehicle.safety.minimum_pose_confidence", unresolved)
    require_number(safety.get("maximum_pose_age_s"), "vehicle.safety.maximum_pose_age_s", unresolved)
    if safety.get("motor_output_enabled") is not False:
        raise ConfigError("vehicle.safety.motor_output_enabled must remain false before hardware validation")
    if safety.get("stop_on_localization_loss") is not True:
        raise ConfigError("vehicle.safety.stop_on_localization_loss must be true")
    return unresolved


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate visual-navigation configuration files.")
    parser.add_argument("--config-dir", type=Path, default=Path(__file__).resolve().parent / "config")
    parser.add_argument("--allow-unset", action="store_true", help="Check structure while calibration values are still unset")
    args = parser.parse_args()

    camera = load_json(args.config_dir / "camera.json")
    vehicle = load_json(args.config_dir / "vehicle.json")
    unresolved = validate_camera(camera) + validate_vehicle(vehicle)
    calibrated = camera["calibration_status"] == "CALIBRATED" and vehicle["calibration_status"] == "CALIBRATED"

    if unresolved or not calibrated:
        message = "Configuration is not ready for autonomous control."
        if unresolved:
            message += " Unset values: " + ", ".join(unresolved)
        if not args.allow_unset:
            raise SystemExit(message)
        print(message)
        return
    print("Configuration is calibrated and structurally valid. Motor output remains disabled by configuration.")


if __name__ == "__main__":
    main()
