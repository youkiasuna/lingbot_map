def write_latest_page(
    session_name: str,
    scene_path: str,
    status_path: str,
    viewer_path: str,
) -> None:
    """Create a lightweight live status page."""

    html = """<!doctype html>
<html lang="en">

<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>LingBot Live Mapping</title>

<style>
body {
    margin: 0;
    min-height: 100vh;
    display: grid;
    place-items: center;
    background: #f4f6f7;
    color: #172026;
    font-family: system-ui, sans-serif;
}

main {
    width: min(650px, calc(100vw - 32px));
    padding: 24px;
    background: #ffffff;
    border: 1px solid #ccd5db;
    border-radius: 10px;
}

h1 {
    margin: 0 0 14px;
    font-size: 22px;
}

p {
    margin: 10px 0;
    color: #5f6d76;
    line-height: 1.5;
}

code {
    background: #eef2f4;
    padding: 2px 5px;
    border-radius: 4px;
}

a {
    color: #087f8c;
}

#state {
    font-weight: 700;
    color: #172026;
}

#ready {
    font-weight: 700;
}
</style>
</head>

<body>

<main>

<h1>LingBot Live Mapping</h1>

<p>
Session:
<code>__SESSION_NAME__</code>
</p>

<p>
Pipeline:
<span id="state">starting...</span>
</p>

<p>
Frames captured:
<strong id="captured">0</strong>
</p>

<p>
Frames processed:
<strong id="processed">0</strong>
</p>

<p>
Mapping updates:
<strong id="updates">0</strong>
</p>

<p id="ready">
Waiting for first point cloud...
</p>

<p>
<a href="__SCENE_PATH__" target="_blank">
Open live_scene.json
</a>
</p>

<p>
<a href="__VIEWER_PATH__" target="_blank">
Open derived 3D viewer
</a>
(only available when --with-derived-map is enabled)
</p>

</main>

<script>

const statusURL = "__STATUS_PATH__";
const sceneURL = "__SCENE_PATH__";

let lastUpdate = -1;

async function refreshStatus() {
    try {
        const response = await fetch(
            statusURL + "?t=" + Date.now(),
            {
                cache: "no-store"
            }
        );

        if (response.ok) {
            const status = await response.json();

            document.getElementById("state").textContent =
                status.state ?? "unknown";

            document.getElementById("captured").textContent =
                status.frames_captured ?? 0;

            document.getElementById("processed").textContent =
                status.frames_processed ?? 0;

            document.getElementById("updates").textContent =
                status.updates_completed ?? 0;

            const updates =
                status.updates_completed ?? 0;

            if (updates > 0) {
                document.getElementById("ready").textContent =
                    "Live point cloud ready - update #" + updates;

                if (updates !== lastUpdate) {
                    console.log(
                        "New LingBot map available:",
                        updates
                    );

                    lastUpdate = updates;

                    await checkScene();
                }
            } else {
                document.getElementById("ready").textContent =
                    "Waiting for first point cloud...";
            }

            if (status.last_error) {
                document.getElementById("ready").textContent =
                    "ERROR: " + status.last_error;
            }
        }
    } catch (error) {
        console.debug(
            "Waiting for pipeline status...",
            error
        );
    }

    setTimeout(refreshStatus, 1000);
}

async function checkScene() {
    try {
        const response = await fetch(
            sceneURL + "?t=" + Date.now(),
            {
                cache: "no-store"
            }
        );

        if (response.ok) {
            const scene = await response.json();

            console.log(
                "live_scene.json updated",
                scene
            );
        }
    } catch (error) {
        console.debug(
            "Waiting for live scene...",
            error
        );
    }
}

refreshStatus();

</script>

</body>
</html>
"""

    html = (
        html
        .replace("__SESSION_NAME__", session_name)
        .replace("__SCENE_PATH__", scene_path)
        .replace("__STATUS_PATH__", status_path)
        .replace("__VIEWER_PATH__", viewer_path)
    )

    LATEST_PAGE.write_text(
        html,
        encoding="utf-8",
    )
def start_server(
    host: str,
    port: int,
) -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(
        QuietHandler,
        directory=str(PROJECT_DIR),
    )

    last_error: OSError | None = None

    for candidate in range(port, port + 20):
        try:
            server = http.server.ThreadingHTTPServer(
                (host, candidate),
                handler,
            )

            thread = threading.Thread(
                target=server.serve_forever,
                name="static-server",
                daemon=True,
            )
            thread.start()

            return server, candidate

        except OSError as exc:
            last_error = exc

    raise SystemExit(
        f"Could not start HTTP server near port {port}: {last_error}"
    )


def local_ips() -> list[str]:
    found: set[str] = set()

    try:
        for info in socket.getaddrinfo(
            socket.gethostname(),
            None,
            socket.AF_INET,
        ):
            ip = info[4][0]

            if not ip.startswith("127."):
                found.add(ip)

    except OSError:
        pass

    return sorted(found)


def build_pipeline_command(
    args: argparse.Namespace,
    session_name: str,
) -> list[str]:
    command = [
        sys.executable,
        str(PIPELINE),

        "--url",
        args.url,

        "--session-root",
        str(SESSION_ROOT),

        "--session-name",
        session_name,

        "--managed-by-server",

        "--model-path",
        str(args.model_path),

        "--fps",
        str(args.fps),

        "--batch-frames",
        str(args.batch_frames),

        "--process-every",
        str(args.process_every),

        "--max-frames",
        str(args.max_frames),

        "--warmup-frames",
        str(args.warmup_frames),

        "--jpeg-quality",
        str(args.jpeg_quality),

        "--rotate",
        args.rotate,

        "--image-size",
        str(args.image_size),

        "--downsample-factor",
        str(args.downsample_factor),

        "--sample-stride",
        str(args.sample_stride),

        "--camera-num-iterations",
        str(args.camera_num_iterations),

        "--conf-threshold",
        str(args.conf_threshold),
    ]

    if args.use_sdpa:
        command.append("--use-sdpa")

    if args.with_derived_map:
        command.append("--with-derived-map")

    return command


def main() -> int:
    args = parse_args()

    session_name = safe_session_name(
        args.session_name
    )

    SESSION_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    session_dir = SESSION_ROOT / session_name

    if session_dir.exists():
        raise SystemExit(
            f"Session already exists: {session_dir}"
        )

    viewer_path = viewer_relative_path(
        session_dir
    )

    scene_path = scene_relative_path(
        session_dir
    )

    status_path = status_relative_path(
        session_dir
    )

    write_latest_page(
        session_name,
        scene_path,
        status_path,
        viewer_path,
    )

    server: http.server.ThreadingHTTPServer | None = None
    served_port = args.port

    if not args.no_server:
        server, served_port = start_server(
            args.host,
            args.port,
        )

        print(
            f"Live mapping page: "
            f"http://127.0.0.1:{served_port}/latest.html",
            flush=True,
        )

        for ip in local_ips():
            print(
                f"LAN live mapping page: "
                f"http://{ip}:{served_port}/latest.html",
                flush=True,
            )

    else:
        print(
            f"Live mapping page file: {LATEST_PAGE}",
            flush=True,
        )

    print(
        f"Session output: {session_dir}",
        flush=True,
    )

    print(
        f"First mapping update after "
        f"{args.batch_frames} frames.",
        flush=True,
    )

    print(
        f"Requested update interval: "
        f"{args.process_every} new frames.",
        flush=True,
    )

    if args.with_derived_map:
        print(
            "Derived replay map: ENABLED (slower)",
            flush=True,
        )
    else:
        print(
            "Derived replay map: DISABLED "
            "(recommended for live mode)",
            flush=True,
        )

    command = build_pipeline_command(
        args,
        session_name,
    )

    try:
        return subprocess.run(
            command,
            cwd=ROOT,
        ).returncode

    finally:
        expected_scene = (
            session_dir
            / "live_scene.json"
        )

        expected_viewer = (
            session_dir
            / "online_replay"
            / "latest"
            / VIEWER_NAME
        )

        print(
            f"Live scene: {expected_scene}",
            flush=True,
        )

        if args.with_derived_map:
            print(
                f"Derived viewer: {expected_viewer}",
                flush=True,
            )

        if server is not None:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())