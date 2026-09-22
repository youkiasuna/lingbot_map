#!/usr/bin/env python3
"""Minimal live LingBot-MAP point-cloud updater.

Only does:
    IP camera -> LingBot-MAP streaming inference -> cumulative PLY updates

It does NOT depend on Integrated_version and does NOT provide navigation,
TSDF, classification, or replay. A lightweight Viser web viewer shows the
point cloud while it is being updated.

Example:
    python "Tony's project/live_pointcloud/run_live_pointcloud.py" \
        --url http://192.168.50.98:8080/video \
        --model-path models/lingbot-map.pt \
        --use-sdpa
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import threading
import webbrowser
from pathlib import Path

# Reduce CUDA allocator fragmentation. Must be set before importing torch.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision.transforms.functional import to_tensor


ROOT = Path(__file__).resolve().parents[2]
LINGBOT_ROOT = ROOT / "lingbot-map-main"
if str(LINGBOT_ROOT) not in sys.path:
    sys.path.insert(0, str(LINGBOT_ROOT))

from lingbot_map.models.gct_stream import GCTStream

try:
    import viser
except ImportError:
    viser = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live IP-camera -> LingBot-MAP -> updating PLY point cloud"
    )
    parser.add_argument("--url", default=None, help="IP camera MJPEG/RTSP URL. If omitted, you will be prompted at startup.")
    parser.add_argument(
        "--model-path",
        type=Path,
        default=ROOT / "models" / "lingbot-map.pt",
        help="LingBot-MAP checkpoint",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "outputs" / "live_pointcloud.ply",
    )
    parser.add_argument("--fps", type=float, default=2.0, help="Frames sent to the model per second")
    parser.add_argument("--port", type=int, default=8080, help="Live 3D viewer web port")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the viewer in a browser")
    parser.add_argument("--num-scale-frames", type=int, default=8)
    parser.add_argument("--image-size", type=int, default=518)
    parser.add_argument("--patch-size", type=int, default=14)
    parser.add_argument("--kv-cache-sliding-window", type=int, default=64)
    parser.add_argument("--keyframe-interval", type=int, default=1)
    parser.add_argument("--camera-num-iterations", type=int, default=1)
    parser.add_argument("--conf-threshold", type=float, default=1.5)
    parser.add_argument(
        "--sample-stride",
        type=int,
        default=8,
        help="Keep one point every N pixels. Larger = faster/smaller PLY.",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=1_000_000,
        help="Maximum accumulated points kept in the live PLY; 0 = unlimited.",
    )
    parser.add_argument("--jpeg-quality", type=int, default=90)
    parser.add_argument(
        "--rotate",
        choices=("none", "cw90", "ccw90", "180"),
        default="none",
    )
    parser.add_argument(
        "--use-sdpa",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use PyTorch SDPA backend (recommended when FlashInfer is unavailable).",
    )
    args = parser.parse_args()

    if not args.url:
        args.url = input("Camera URL (example http://192.168.1.100:8080/video): ").strip()
        if not args.url:
            parser.error("camera URL cannot be empty")
    if args.fps <= 0:
        parser.error("--fps must be > 0")
    if args.num_scale_frames < 2:
        parser.error("--num-scale-frames must be >= 2")
    if args.sample_stride < 1:
        parser.error("--sample-stride must be >= 1")
    if args.keyframe_interval < 1:
        parser.error("--keyframe-interval must be >= 1")
    if not args.model_path.is_file():
        parser.error(f"checkpoint not found: {args.model_path}")
    return args


def rotate_frame(frame: np.ndarray, mode: str) -> np.ndarray:
    if mode == "cw90":
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if mode == "ccw90":
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if mode == "180":
        return cv2.rotate(frame, cv2.ROTATE_180)
    return frame


def preprocess_bgr(frame: np.ndarray, image_size: int, patch_size: int) -> torch.Tensor:
    """Match lingbot_map.utils.load_fn crop preprocessing, but without writing JPEGs."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    width, height = img.size

    new_width = image_size
    new_height = round(height * (new_width / width) / patch_size) * patch_size
    img = img.resize((new_width, new_height), Image.Resampling.BICUBIC)
    tensor = to_tensor(img)

    if new_height > image_size:
        start_y = (new_height - image_size) // 2
        tensor = tensor[:, start_y : start_y + image_size, :]

    return tensor


def load_model(args: argparse.Namespace, device: torch.device) -> GCTStream:
    print("Building LingBot-MAP streaming model...", flush=True)
    model = GCTStream(
        img_size=args.image_size,
        patch_size=args.patch_size,
        enable_3d_rope=True,
        max_frame_num=4096,
        kv_cache_sliding_window=args.kv_cache_sliding_window,
        kv_cache_scale_frames=args.num_scale_frames,
        kv_cache_cross_frame_special=True,
        kv_cache_include_scale_frames=True,
        use_sdpa=args.use_sdpa,
        camera_num_iterations=args.camera_num_iterations,
    )

    print(f"Loading checkpoint: {args.model_path}", flush=True)
    checkpoint = torch.load(args.model_path, map_location=device, weights_only=False)
    state_dict = checkpoint.get("model", checkpoint)
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    print(
        f"Checkpoint loaded (missing={len(missing)}, unexpected={len(unexpected)})",
        flush=True,
    )

    model = model.to(device).eval()
    return model


def prediction_to_points(
    model: GCTStream,
    output: dict,
    images: torch.Tensor,
    conf_threshold: float,
    sample_stride: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert one LingBot output block into filtered XYZ + RGB points."""
    world_points = output.get("world_points")
    confidence = output.get("world_points_conf")

    if world_points is None:
        if "depth" not in output or "pose_enc" not in output:
            raise RuntimeError("LingBot output has neither world_points nor depth+pose_enc")
        world_points = model._unproject_depth_to_world(output["depth"], output["pose_enc"])
        confidence = output.get("depth_conf")

    pts = world_points[0].detach().float().cpu().numpy()
    imgs = images[0].detach().float().cpu().numpy().transpose(0, 2, 3, 1)

    if confidence is None:
        conf = np.ones(pts.shape[:-1], dtype=np.float32)
    else:
        conf = confidence[0].detach().float().cpu().numpy()

    pts = pts[:, ::sample_stride, ::sample_stride, :].reshape(-1, 3)
    cols = imgs[:, ::sample_stride, ::sample_stride, :].reshape(-1, 3)
    conf = conf[:, ::sample_stride, ::sample_stride].reshape(-1)

    valid = np.isfinite(pts).all(axis=1) & np.isfinite(conf)
    valid &= conf > conf_threshold
    pts = pts[valid].astype(np.float32, copy=False)
    cols = (np.clip(cols[valid], 0.0, 1.0) * 255.0).astype(np.uint8)
    return pts, cols


def write_ply_atomic(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    """Write a binary PLY then atomically replace the previous live cloud."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")

    dtype = np.dtype(
        [
            ("x", "<f4"),
            ("y", "<f4"),
            ("z", "<f4"),
            ("red", "u1"),
            ("green", "u1"),
            ("blue", "u1"),
        ]
    )
    rows = np.empty(len(points), dtype=dtype)
    rows["x"], rows["y"], rows["z"] = points[:, 0], points[:, 1], points[:, 2]
    rows["red"], rows["green"], rows["blue"] = colors[:, 0], colors[:, 1], colors[:, 2]

    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "comment live LingBot-MAP point cloud\n"
        f"element vertex {len(points)}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    )
    with tmp.open("wb") as handle:
        handle.write(header.encode("ascii"))
        rows.tofile(handle)
    os.replace(tmp, path)


class PointAccumulator:
    def __init__(self, max_points: int):
        self.max_points = max_points
        self.points: list[np.ndarray] = []
        self.colors: list[np.ndarray] = []
        self.count = 0

    def add(self, points: np.ndarray, colors: np.ndarray) -> None:
        if len(points) == 0:
            return
        self.points.append(points)
        self.colors.append(colors)
        self.count += len(points)

        if self.max_points > 0 and self.count > self.max_points:
            # Keep the newest cloud data. This bounds RAM and PLY write time.
            while len(self.points) > 1 and self.count - len(self.points[0]) >= self.max_points:
                self.count -= len(self.points[0])
                self.points.pop(0)
                self.colors.pop(0)

    def arrays(self) -> tuple[np.ndarray, np.ndarray]:
        if not self.points:
            return (
                np.empty((0, 3), dtype=np.float32),
                np.empty((0, 3), dtype=np.uint8),
            )
        points = np.concatenate(self.points, axis=0)
        colors = np.concatenate(self.colors, axis=0)
        if self.max_points > 0 and len(points) > self.max_points:
            points = points[-self.max_points :]
            colors = colors[-self.max_points :]
        return points, colors


def infer_block(
    model: GCTStream,
    images: torch.Tensor,
    scale_frames: int,
    dtype: torch.dtype,
    device: torch.device,
    num_frame_per_block: int,
) -> dict:
    images = images.to(device, non_blocking=True)
    amp_enabled = device.type == "cuda"
    with torch.no_grad(), torch.amp.autocast(
        device_type=device.type,
        dtype=dtype,
        enabled=amp_enabled,
    ):
        return model.forward(
            images,
            num_frame_for_scale=scale_frames,
            num_frame_per_block=num_frame_per_block,
            causal_inference=True,
        )


class LiveWebViewer:
    """Very small Viser viewer whose single point cloud is updated in-place."""

    def __init__(self, port: int):
        if viser is None:
            raise RuntimeError(
                "viser is not installed. Run: pip install -e 'lingbot-map-main[vis]'"
            )
        self.server = viser.ViserServer(host="0.0.0.0", port=port)
        self.server.gui.configure_theme(titlebar_content=None, control_layout="collapsible")
        self.handle = None
        self.center = None
        self.lock = threading.Lock()

    def update(self, points: np.ndarray, colors: np.ndarray) -> None:
        if len(points) == 0:
            return
        with self.lock:
            if self.center is None:
                self.center = np.median(points, axis=0).astype(np.float32)
            shown = points - self.center
            if self.handle is None:
                self.handle = self.server.scene.add_point_cloud(
                    "/live_pointcloud",
                    points=shown,
                    colors=colors,
                    point_size=0.002,
                    point_shape="circle",
                )
            else:
                self.handle.points = shown
                self.handle.colors = colors


def main() -> int:
    args = parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        print("WARNING: CUDA not found. Live inference will be very slow.", flush=True)

    dtype = (
        torch.bfloat16
        if device.type == "cuda" and torch.cuda.get_device_capability()[0] >= 8
        else torch.float16
        if device.type == "cuda"
        else torch.float32
    )

    model = load_model(args, device)
    if dtype != torch.float32 and getattr(model, "aggregator", None) is not None:
        model.aggregator = model.aggregator.to(dtype=dtype)

    model.clean_kv_cache()
    accumulator = PointAccumulator(args.max_points)

    viewer = LiveWebViewer(args.port)
    viewer_url = f"http://127.0.0.1:{args.port}"
    print(f"Live 3D viewer: {viewer_url}", flush=True)
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(viewer_url)).start()

    cap = cv2.VideoCapture(
        args.url,
        cv2.CAP_FFMPEG,
        [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            10000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            10000,
        ],
    )
    if not cap.isOpened():
        raise SystemExit(f"Unable to open camera stream: {args.url}")

    print(f"Device: {device} / dtype: {dtype}", flush=True)
    print(f"Output PLY: {args.output}", flush=True)
    print(
        f"Collecting {args.num_scale_frames} initial scale frames, then true frame-by-frame KV-cache streaming.",
        flush=True,
    )
    print("Press Ctrl+C to stop.", flush=True)

    initial_frames: list[torch.Tensor] = []
    frame_index = 0
    next_capture = time.perf_counter()
    period = 1.0 / args.fps

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("Camera read failed; retrying...", flush=True)
                time.sleep(0.2)
                continue

            now = time.perf_counter()
            if now < next_capture:
                continue
            next_capture = now + period

            frame = rotate_frame(frame, args.rotate)
            tensor = preprocess_bgr(frame, args.image_size, args.patch_size)

            if len(initial_frames) < args.num_scale_frames:
                initial_frames.append(tensor)
                print(
                    f"Scale frames: {len(initial_frames)}/{args.num_scale_frames}",
                    flush=True,
                )
                if len(initial_frames) < args.num_scale_frames:
                    continue

                block = torch.stack(initial_frames, dim=0).unsqueeze(0)
                output = infer_block(
                    model,
                    block,
                    args.num_scale_frames,
                    dtype,
                    device,
                    args.num_scale_frames,
                )
                pts, cols = prediction_to_points(
                    model,
                    output,
                    block,
                    args.conf_threshold,
                    args.sample_stride,
                )
                accumulator.add(pts, cols)
                frame_index = args.num_scale_frames
                del output, block
            else:
                block = tensor.unsqueeze(0).unsqueeze(0)
                stream_index = frame_index - args.num_scale_frames
                is_keyframe = (
                    args.keyframe_interval <= 1
                    or stream_index % args.keyframe_interval == 0
                )
                if not is_keyframe:
                    model._set_skip_append(True)
                try:
                    output = infer_block(
                        model,
                        block,
                        args.num_scale_frames,
                        dtype,
                        device,
                        1,
                    )
                finally:
                    if not is_keyframe:
                        model._set_skip_append(False)

                pts, cols = prediction_to_points(
                    model,
                    output,
                    block,
                    args.conf_threshold,
                    args.sample_stride,
                )
                accumulator.add(pts, cols)
                frame_index += 1
                del output, block

            points, colors = accumulator.arrays()
            if len(points):
                write_ply_atomic(args.output, points, colors)
                viewer.update(points, colors)

            cache_info = model.get_kv_cache_info()
            print(
                f"frame={frame_index:05d}  new_points={len(pts):7d}  "
                f"cloud={len(points):8d}  "
                f"kv={cache_info.get('cache_memory_mb', 0):.1f}MB  "
                f"saved={args.output.name}",
                flush=True,
            )

    except KeyboardInterrupt:
        print("\nStopping live point-cloud update.", flush=True)
    finally:
        cap.release()
        model.clean_kv_cache()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
