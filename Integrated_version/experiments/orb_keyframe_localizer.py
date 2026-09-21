#!/usr/bin/env python3
"""ORB keyframe retrieval + PnP localizer for the LingBot map package."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


INTEGRATED_ROOT = Path(__file__).resolve().parents[1]
if str(INTEGRATED_ROOT) not in sys.path:
    sys.path.insert(0, str(INTEGRATED_ROOT))

from localization.localizer_interface import FilePosePublisher, PoseSample  # noqa: E402


@dataclass
class ReferenceFrame:
    index: int
    image_path: Path
    keypoints_xy: np.ndarray
    descriptors: np.ndarray | None


@dataclass
class CandidateResult:
    frame_index: int
    image_path: str
    match_count: int
    pnp_status: str
    inlier_count: int
    inlier_ratio: float
    reprojection_error_px: float | None
    confidence: float
    position_xyz: list[float] | None
    yaw_deg: float | None


@dataclass(frozen=True)
class PreprocessInfo:
    original_width: int
    original_height: int
    processed_width: int
    processed_height: int
    resize_mode: str
    scale_x: float
    scale_y: float
    crop_x: int = 0
    crop_y: int = 0
    pad_x: int = 0
    pad_y: int = 0

    @property
    def original_aspect_ratio(self) -> float:
        return self.original_width / max(float(self.original_height), 1.0)

    @property
    def processed_aspect_ratio(self) -> float:
        return self.processed_width / max(float(self.processed_height), 1.0)

    def to_payload(self) -> dict[str, Any]:
        return {
            "original_resolution": [self.original_width, self.original_height],
            "processed_resolution": [self.processed_width, self.processed_height],
            "resize_mode": self.resize_mode,
            "original_aspect_ratio": round(self.original_aspect_ratio, 6),
            "processed_aspect_ratio": round(self.processed_aspect_ratio, 6),
            "scale_x": round(self.scale_x, 6),
            "scale_y": round(self.scale_y, 6),
            "crop_xy": [self.crop_x, self.crop_y],
            "pad_xy": [self.pad_x, self.pad_y],
        }


def read_image(
    path_or_image: Path | np.ndarray,
    target_size: tuple[int, int],
    resize_mode: str = "stretch",
) -> tuple[np.ndarray, PreprocessInfo]:
    if isinstance(path_or_image, np.ndarray):
        image = path_or_image
    else:
        image = cv2.imread(str(path_or_image), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Failed to read image: {path_or_image}")
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Input image must be a BGR/RGB color image with three channels")

    width, height = target_size
    original_height, original_width = int(image.shape[0]), int(image.shape[1])
    if resize_mode not in {"stretch", "letterbox", "cover_crop"}:
        raise ValueError(f"Unsupported resize mode: {resize_mode}")

    if original_width == width and original_height == height:
        return image, PreprocessInfo(
            original_width=original_width,
            original_height=original_height,
            processed_width=width,
            processed_height=height,
            resize_mode=resize_mode,
            scale_x=1.0,
            scale_y=1.0,
        )

    if resize_mode == "stretch":
        resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
        return resized, PreprocessInfo(
            original_width=original_width,
            original_height=original_height,
            processed_width=width,
            processed_height=height,
            resize_mode=resize_mode,
            scale_x=width / max(float(original_width), 1.0),
            scale_y=height / max(float(original_height), 1.0),
        )

    if resize_mode == "letterbox":
        scale = min(width / max(float(original_width), 1.0), height / max(float(original_height), 1.0))
        resized_width = max(1, int(round(original_width * scale)))
        resized_height = max(1, int(round(original_height * scale)))
        resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((height, width, 3), dtype=image.dtype)
        pad_x = (width - resized_width) // 2
        pad_y = (height - resized_height) // 2
        canvas[pad_y : pad_y + resized_height, pad_x : pad_x + resized_width] = resized
        return canvas, PreprocessInfo(
            original_width=original_width,
            original_height=original_height,
            processed_width=width,
            processed_height=height,
            resize_mode=resize_mode,
            scale_x=scale,
            scale_y=scale,
            pad_x=pad_x,
            pad_y=pad_y,
        )

    scale = max(width / max(float(original_width), 1.0), height / max(float(original_height), 1.0))
    resized_width = max(1, int(round(original_width * scale)))
    resized_height = max(1, int(round(original_height * scale)))
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
    crop_x = max((resized_width - width) // 2, 0)
    crop_y = max((resized_height - height) // 2, 0)
    cropped = resized[crop_y : crop_y + height, crop_x : crop_x + width]
    if cropped.shape[1] != width or cropped.shape[0] != height:
        cropped = cv2.resize(cropped, (width, height), interpolation=cv2.INTER_AREA)
    return cropped, PreprocessInfo(
        original_width=original_width,
        original_height=original_height,
        processed_width=width,
        processed_height=height,
        resize_mode=resize_mode,
        scale_x=scale,
        scale_y=scale,
        crop_x=crop_x,
        crop_y=crop_y,
    )


def keypoints_to_xy(keypoints: tuple[cv2.KeyPoint, ...] | list[cv2.KeyPoint]) -> np.ndarray:
    return np.asarray([kp.pt for kp in keypoints], dtype=np.float32)


def extract_orb(image: np.ndarray, max_features: int) -> tuple[np.ndarray, np.ndarray | None]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=max_features)
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    if not keypoints:
        return np.empty((0, 2), dtype=np.float32), None
    return keypoints_to_xy(keypoints), descriptors


def load_map_archive(mapping_dir: Path) -> dict[str, np.ndarray]:
    archive_path = mapping_dir / "predictions.npz"
    if not archive_path.is_file():
        raise FileNotFoundError(f"Missing map archive: {archive_path}")
    with np.load(archive_path, allow_pickle=False) as data:
        archive = {name: data[name] for name in data.files}
    required = {"world_points", "intrinsic", "extrinsic_c2w"}
    missing = sorted(required - archive.keys())
    if missing:
        raise ValueError(f"Map archive is missing required arrays: {', '.join(missing)}")
    return archive


def load_reference_frames(mapping_dir: Path, max_features: int, frame_stride: int) -> list[ReferenceFrame]:
    if frame_stride < 1:
        raise ValueError("frame_stride must be positive")
    archive = load_map_archive(mapping_dir)
    world_points = archive["world_points"]
    frame_count = int(world_points.shape[0])
    height, width = int(world_points.shape[1]), int(world_points.shape[2])
    preprocessed_dir = mapping_dir / "preprocessed"
    references: list[ReferenceFrame] = []

    for frame_index in range(0, frame_count, frame_stride):
        image_path = preprocessed_dir / f"{frame_index:06d}.png"
        if not image_path.is_file():
            continue
        image, _ = read_image(image_path, (width, height), resize_mode="stretch")
        keypoints_xy, descriptors = extract_orb(image, max_features)
        references.append(
            ReferenceFrame(
                index=frame_index,
                image_path=image_path,
                keypoints_xy=keypoints_xy,
                descriptors=descriptors,
            )
        )
    if not references:
        raise ValueError(f"No reference frames found in {preprocessed_dir}")
    return references


def match_descriptors(
    query_descriptors: np.ndarray | None,
    reference_descriptors: np.ndarray | None,
    ratio: float,
) -> list[cv2.DMatch]:
    if query_descriptors is None or reference_descriptors is None:
        return []
    if len(query_descriptors) < 2 or len(reference_descriptors) < 2:
        return []
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    pairs = matcher.knnMatch(query_descriptors, reference_descriptors, k=2)
    good: list[cv2.DMatch] = []
    for pair in pairs:
        if len(pair) != 2:
            continue
        best, second = pair
        if best.distance < ratio * second.distance:
            good.append(best)
    return sorted(good, key=lambda match: match.distance)


def lookup_2d_3d_correspondences(
    matches: list[cv2.DMatch],
    query_keypoints_xy: np.ndarray,
    reference: ReferenceFrame,
    world_points: np.ndarray,
    max_pnp_points: int,
    min_world_norm: float,
) -> tuple[np.ndarray, np.ndarray]:
    object_points: list[np.ndarray] = []
    image_points: list[np.ndarray] = []
    frame_world = world_points[reference.index]
    height, width = frame_world.shape[:2]

    for match in matches[:max_pnp_points]:
        ref_x, ref_y = reference.keypoints_xy[match.trainIdx]
        pixel_x = int(round(float(ref_x)))
        pixel_y = int(round(float(ref_y)))
        if pixel_x < 0 or pixel_x >= width or pixel_y < 0 or pixel_y >= height:
            continue
        xyz = np.asarray(frame_world[pixel_y, pixel_x], dtype=np.float32)
        if not np.all(np.isfinite(xyz)):
            continue
        if float(np.linalg.norm(xyz)) < min_world_norm:
            continue
        object_points.append(xyz)
        image_points.append(np.asarray(query_keypoints_xy[match.queryIdx], dtype=np.float32))

    if not object_points:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 2), dtype=np.float32)
    return np.asarray(object_points, dtype=np.float32), np.asarray(image_points, dtype=np.float32)


def pose_from_pnp(
    object_points: np.ndarray,
    image_points: np.ndarray,
    camera_matrix: np.ndarray,
    reprojection_error_px: float,
    iterations: int,
) -> tuple[np.ndarray, float, int, float] | None:
    if len(object_points) < 4:
        return None
    ok, rvec, tvec, inliers = cv2.solvePnPRansac(
        object_points,
        image_points,
        camera_matrix.astype(np.float64),
        None,
        iterationsCount=iterations,
        reprojectionError=reprojection_error_px,
        confidence=0.99,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok or inliers is None or len(inliers) < 4:
        return None

    inlier_indices = inliers.reshape(-1)
    rmat, _ = cv2.Rodrigues(rvec)
    camera_center = (-rmat.T @ tvec).reshape(3)

    projected, _ = cv2.projectPoints(
        object_points[inlier_indices],
        rvec,
        tvec,
        camera_matrix.astype(np.float64),
        None,
    )
    residuals = projected.reshape(-1, 2) - image_points[inlier_indices]
    mean_reprojection_error = float(np.mean(np.linalg.norm(residuals, axis=1)))

    camera_to_world = rmat.T
    forward = camera_to_world @ np.asarray([0.0, 0.0, 1.0])
    yaw_deg = math.degrees(math.atan2(float(forward[0]), float(forward[2]))) % 360.0
    return camera_center.astype(np.float64), yaw_deg, int(len(inliers)), mean_reprojection_error


def confidence_score(match_count: int, inlier_count: int, reprojection_error_px: float | None, min_inliers: int) -> float:
    match_term = min(match_count / 80.0, 1.0)
    inlier_term = min(inlier_count / max(float(min_inliers * 2), 1.0), 1.0)
    if reprojection_error_px is None:
        reprojection_term = 0.0
    else:
        reprojection_term = max(0.0, min(1.0, 1.0 - reprojection_error_px / 10.0))
    return float(round(0.25 * match_term + 0.55 * inlier_term + 0.20 * reprojection_term, 4))


class OrbKeyframeLocalizer:
    def __init__(
        self,
        mapping_dir: Path,
        max_features: int = 2000,
        frame_stride: int = 1,
        ratio: float = 0.75,
        top_k: int = 5,
        min_matches: int = 25,
        min_inliers: int = 12,
        max_pnp_points: int = 300,
        reprojection_error_px: float = 5.0,
        pnp_iterations: int = 200,
        min_world_norm: float = 1e-6,
    ) -> None:
        self.mapping_dir = mapping_dir
        self.archive = load_map_archive(mapping_dir)
        self.world_points = self.archive["world_points"]
        self.intrinsics = self.archive["intrinsic"]
        self.height = int(self.world_points.shape[1])
        self.width = int(self.world_points.shape[2])
        self.max_features = max_features
        self.frame_stride = frame_stride
        self.ratio = ratio
        self.top_k = top_k
        self.min_matches = min_matches
        self.min_inliers = min_inliers
        self.max_pnp_points = max_pnp_points
        self.reprojection_error_px = reprojection_error_px
        self.pnp_iterations = pnp_iterations
        self.min_world_norm = min_world_norm
        self.references = load_reference_frames(mapping_dir, max_features, frame_stride)

    def localize(self, query_image: Path, resize_mode: str = "stretch") -> dict[str, Any]:
        """Localize an image file while preserving the batch API."""
        query_bgr, preprocess = read_image(query_image, (self.width, self.height), resize_mode)
        return self._localize_image(query_bgr, str(query_image), preprocess)

    def localize_frame(
        self,
        frame: np.ndarray,
        query_id: str = "camera_frame",
        resize_mode: str = "cover_crop",
    ) -> dict[str, Any]:
        """Localize one already-captured BGR frame without disk I/O."""
        query_bgr, preprocess = read_image(frame, (self.width, self.height), resize_mode)
        return self._localize_image(query_bgr, query_id, preprocess)

    def _localize_image(
        self,
        query_bgr: np.ndarray,
        query_id: str,
        preprocess: PreprocessInfo,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        query_keypoints_xy, query_descriptors = extract_orb(query_bgr, self.max_features)

        ranked: list[tuple[ReferenceFrame, list[cv2.DMatch]]] = []
        for reference in self.references:
            matches = match_descriptors(query_descriptors, reference.descriptors, self.ratio)
            if matches:
                ranked.append((reference, matches))
        ranked.sort(key=lambda item: len(item[1]), reverse=True)

        candidates: list[CandidateResult] = []
        best: CandidateResult | None = None
        for reference, matches in ranked[: self.top_k]:
            object_points, image_points = lookup_2d_3d_correspondences(
                matches,
                query_keypoints_xy,
                reference,
                self.world_points,
                self.max_pnp_points,
                self.min_world_norm,
            )
            pnp = None
            if len(matches) >= self.min_matches:
                pnp = pose_from_pnp(
                    object_points,
                    image_points,
                    self.intrinsics[reference.index],
                    self.reprojection_error_px,
                    self.pnp_iterations,
                )

            if pnp is None:
                inlier_count = 0
                reprojection_error = None
                position = None
                yaw = None
                pnp_status = "not_enough_geometry"
            else:
                camera_center, yaw, inlier_count, reprojection_error = pnp
                position = [round(float(value), 5) for value in camera_center.tolist()]
                pnp_status = "ok" if inlier_count >= self.min_inliers else "low_inliers"

            confidence = confidence_score(len(matches), inlier_count, reprojection_error, self.min_inliers)
            candidate = CandidateResult(
                frame_index=reference.index,
                image_path=str(reference.image_path),
                match_count=len(matches),
                pnp_status=pnp_status,
                inlier_count=inlier_count,
                inlier_ratio=round(inlier_count / max(len(matches), 1), 4),
                reprojection_error_px=None if reprojection_error is None else round(float(reprojection_error), 4),
                confidence=confidence,
                position_xyz=position,
                yaw_deg=None if yaw is None else round(float(yaw), 2),
            )
            candidates.append(candidate)
            if best is None or (candidate.confidence, candidate.inlier_count, candidate.match_count) > (
                best.confidence,
                best.inlier_count,
                best.match_count,
            ):
                best = candidate

        latency_ms = round((time.perf_counter() - started_at) * 1000.0, 3)
        status = "lost"
        if best is not None and best.pnp_status == "ok":
            status = "localized"
        elif best is not None:
            status = "low_confidence"

        return {
            "schema_version": 1,
            "method": "orb_keyframe_pnp",
            "query_image": query_id,
            "status": status,
            "preprocessing": preprocess.to_payload(),
            "reference_loading": {
                "frame_stride": self.frame_stride,
                "reference_count": len(self.references),
                "mapping_frame_count": int(self.world_points.shape[0]),
            },
            "camera_model": {
                "mapping_intrinsic_source": "predictions.npz:intrinsic[reference.frame_index]",
                "query_intrinsic_source": "mapping reference intrinsic proxy; RTSP camera intrinsics are not calibrated",
                "pnp_image_size": [self.width, self.height],
            },
            "query_keypoint_count": int(len(query_keypoints_xy)),
            "reference_count": len(self.references),
            "best": None if best is None else asdict(best),
            "candidates": [asdict(candidate) for candidate in candidates],
            "latency_ms": latency_ms,
            "timestamp_unix": time.time(),
            "coordinate_note": "position_xyz is in LingBot reconstruction coordinates; -Y-up scene uses X/Z as the navigation plane.",
        }


class OrbRelocalizer(OrbKeyframeLocalizer):
    """Streaming-oriented name for the reusable ORB relocalizer.

    The implementation inherits the existing batch behavior and adds
    ``localize_frame`` for camera frames. Mapping descriptors and world points
    are still loaded only once during initialization.
    """


def result_to_pose(result: dict[str, Any], min_confidence: float) -> PoseSample:
    best = result.get("best")
    if not isinstance(best, dict):
        return PoseSample(0.0, 0.0, 0.0, time.time(), "orb_keyframe_pnp", 0.0, status="lost")
    position = best.get("position_xyz")
    yaw = best.get("yaw_deg")
    confidence = float(best.get("confidence", 0.0))
    if result.get("status") != "localized" or position is None or yaw is None or confidence < min_confidence:
        status = "low_confidence" if confidence > 0.0 else "lost"
        return PoseSample(
            0.0,
            0.0,
            0.0,
            time.time(),
            "orb_keyframe_pnp",
            confidence,
            status=status,
            inlier_count=int(best.get("inlier_count", 0)),
            reprojection_error_px=best.get("reprojection_error_px"),
            frame_id=str(best.get("frame_index")),
        )
    return PoseSample(
        x_m=float(position[0]),
        y_m=float(position[2]),
        yaw_deg=float(yaw),
        timestamp_unix=time.time(),
        source="orb_keyframe_pnp",
        confidence=confidence,
        status="ok",
        inlier_count=int(best.get("inlier_count", 0)),
        reprojection_error_px=best.get("reprojection_error_px"),
        frame_id=str(best.get("frame_index")),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping-dir", required=True, type=Path)
    parser.add_argument("--query-image", required=True, type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--pose-file", type=Path)
    parser.add_argument("--publish-min-confidence", type=float, default=0.35)
    parser.add_argument("--max-features", type=int, default=2000)
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--resize-mode", choices=("stretch", "letterbox", "cover_crop"), default="stretch")
    parser.add_argument("--ratio", type=float, default=0.75)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-matches", type=int, default=25)
    parser.add_argument("--min-inliers", type=int, default=12)
    parser.add_argument("--max-pnp-points", type=int, default=300)
    parser.add_argument("--reprojection-error-px", type=float, default=5.0)
    parser.add_argument("--pnp-iterations", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    localizer = OrbKeyframeLocalizer(
        mapping_dir=args.mapping_dir,
        max_features=args.max_features,
        frame_stride=args.frame_stride,
        ratio=args.ratio,
        top_k=args.top_k,
        min_matches=args.min_matches,
        min_inliers=args.min_inliers,
        max_pnp_points=args.max_pnp_points,
        reprojection_error_px=args.reprojection_error_px,
        pnp_iterations=args.pnp_iterations,
    )
    result = localizer.localize(args.query_image, resize_mode=args.resize_mode)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.pose_file:
        pose = result_to_pose(result, args.publish_min_confidence)
        FilePosePublisher(args.pose_file).publish(pose)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
