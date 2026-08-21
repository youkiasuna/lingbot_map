import argparse
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


COMMAND_MAP = {
    "forward": "F",
    "backward": "B",
    "left": "L",
    "right": "R",
    "stop": "S",
}


HTML_PAGE = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ESP32 Car Controller</title>
  <style>
    :root {
      --bg: #08111f;
      --panel: rgba(10, 20, 38, 0.9);
      --panel-border: rgba(129, 140, 248, 0.28);
      --text: #e5eefc;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-2: #22c55e;
      --danger: #fb7185;
      --btn: #12213a;
      --btn-hover: #1a2d4f;
      --soft: rgba(15, 23, 42, 0.74);
      --soft-border: rgba(148, 163, 184, 0.18);
      --shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.16), transparent 28%),
        radial-gradient(circle at bottom right, rgba(34, 197, 94, 0.12), transparent 24%),
        linear-gradient(160deg, #050914 0%, #0b1526 50%, #06111c 100%);
      color: var(--text);
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .card {
      width: min(92vw, 560px);
      padding: 28px;
      border-radius: 28px;
      background: var(--panel);
      border: 1px solid var(--panel-border);
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }

    h1 {
      margin: 0 0 8px;
      font-size: clamp(1.6rem, 4vw, 2.2rem);
      letter-spacing: 0.04em;
    }

    .subtitle {
      margin: 0 0 22px;
      color: var(--muted);
      line-height: 1.6;
    }

    .status {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }

    .status-item {
      padding: 14px 16px;
      border-radius: 18px;
      background: var(--soft);
      border: 1px solid var(--soft-border);
      min-width: 0;
    }

    .status-item small,
    .speed-copy small,
    .speed-scale span {
      display: block;
      color: var(--muted);
      margin-bottom: 2px;
    }

    .status-item strong,
    .speed-copy strong {
      display: block;
      font-size: 1.05rem;
      overflow-wrap: anywhere;
    }

    .speed-panel {
      margin: 8px 0 24px;
      padding: 18px;
      border-radius: 20px;
      background: rgba(15, 23, 42, 0.62);
      border: 1px solid rgba(56, 189, 248, 0.18);
    }

    .speed-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 16px;
    }

    .speed-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 92px;
      padding: 10px 12px;
      border-radius: 999px;
      background: rgba(56, 189, 248, 0.16);
      border: 1px solid rgba(56, 189, 248, 0.22);
      color: #d8f3ff;
      font-size: 0.95rem;
      white-space: nowrap;
    }

    .speed-slider {
      width: 100%;
      margin: 0;
      accent-color: var(--accent);
    }

    .speed-scale {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-top: 8px;
      font-size: 0.85rem;
    }

    .speed-actions {
      display: grid;
      grid-template-columns: 56px minmax(0, 1fr) 56px;
      gap: 10px;
      align-items: center;
      margin-top: 16px;
    }

    .speed-presets {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }

    button {
      border: 0;
      color: var(--text);
      background: var(--btn);
      min-width: 88px;
      min-height: 88px;
      border-radius: 22px;
      font-size: 1.8rem;
      cursor: pointer;
      box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.16);
      transition: transform 0.12s ease, background 0.12s ease, box-shadow 0.12s ease;
      user-select: none;
      touch-action: manipulation;
    }

    button:hover {
      background: var(--btn-hover);
      transform: translateY(-1px);
    }

    button:active, button.active {
      transform: translateY(1px) scale(0.98);
      box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.4);
      background: rgba(56, 189, 248, 0.2);
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      align-items: center;
      justify-items: center;
      margin: 24px auto 10px;
      width: min(100%, 360px);
    }

    .forward { color: var(--accent); }
    .backward { color: var(--danger); }
    .left, .right { color: #c4b5fd; }

    .stop {
      color: var(--accent-2);
      min-width: 92px;
      min-height: 56px;
      border-radius: 999px;
      font-size: 1rem;
      letter-spacing: 0.16em;
    }

    .speed-adjust,
    .speed-preset {
      min-width: 0;
      min-height: 52px;
      border-radius: 16px;
      font-size: 1rem;
    }

    .speed-adjust {
      font-size: 1.4rem;
    }

    .hint {
      color: var(--muted);
      margin-top: 18px;
      line-height: 1.7;
      font-size: 0.95rem;
    }

    code {
      padding: 0.18rem 0.42rem;
      border-radius: 8px;
      background: rgba(148, 163, 184, 0.12);
      color: #dbeafe;
    }

    @media (max-width: 480px) {
      .card { padding: 18px; border-radius: 22px; }
      .status { grid-template-columns: 1fr; }
      .grid { width: 100%; }
      button { min-width: 76px; min-height: 76px; }
      .speed-panel { padding: 16px; }
      .speed-head { flex-direction: column; align-items: stretch; }
      .speed-actions { grid-template-columns: 52px minmax(0, 1fr) 52px; }
      .speed-adjust,
      .speed-preset { min-height: 48px; }
    }
  </style>
</head>
<body>
  <main class="card">
    <h1>ESP32 Car Controller</h1>
    <p class="subtitle">長按方向鍵開始移動，放開後自動停止。配速板可以即時調整馬達速度，短點方向鍵不會誤觸移動。</p>

    <section class="status">
      <div class="status-item">
        <small>Current command</small>
        <strong id="status">Idle</strong>
      </div>
      <div class="status-item">
        <small>Target ESP32</small>
        <strong id="target">127.0.0.1:8000</strong>
      </div>
    </section>

    <section class="speed-panel" aria-label="speed controller">
      <div class="speed-head">
        <div class="speed-copy">
          <small>Drive speed</small>
          <strong><span id="speedValue">__DEFAULT_SPEED__</span> / __MAX_SPEED__</strong>
        </div>
        <div class="speed-badge" id="speedBadge">未同步</div>
      </div>

      <input
        id="speedSlider"
        class="speed-slider"
        type="range"
        min="__MIN_SPEED__"
        max="__MAX_SPEED__"
        step="__SPEED_STEP__"
        value="__DEFAULT_SPEED__"
        aria-label="drive speed"
      >

      <div class="speed-scale">
        <span>Min __MIN_SPEED__</span>
        <span>Max __MAX_SPEED__</span>
      </div>

      <div class="speed-actions">
        <button type="button" class="speed-adjust" id="speedDecrease" aria-label="decrease speed">−</button>
        <div class="speed-presets">
          <button type="button" class="speed-preset" data-speed-preset="__PRESET_LOW__">__PRESET_LOW__</button>
          <button type="button" class="speed-preset" data-speed-preset="__PRESET_MID__">__PRESET_MID__</button>
          <button type="button" class="speed-preset" data-speed-preset="__PRESET_HIGH__">__PRESET_HIGH__</button>
        </div>
        <button type="button" class="speed-adjust" id="speedIncrease" aria-label="increase speed">+</button>
      </div>
    </section>

    <div class="grid" aria-label="direction controller">
      <div></div>
      <button class="forward" data-command="forward" aria-label="forward">▲</button>
      <div></div>
      <button class="left" data-command="left" aria-label="left">◀</button>
      <button class="stop" data-command="stop" aria-label="stop">STOP</button>
      <button class="right" data-command="right" aria-label="right">▶</button>
      <div></div>
      <button class="backward" data-command="backward" aria-label="backward">▼</button>
      <div></div>
    </div>

    <p class="hint">
      鍵盤支援：<code>ArrowUp</code> 前進、<code>ArrowDown</code> 後退、<code>ArrowLeft</code> 左轉、<code>ArrowRight</code> 右轉、<code>Space</code> 停止。速度命令預設格式為 <code>V&#123;value&#125;</code>，可用啟動參數覆寫。
    </p>
  </main>

  <script>
    const statusEl = document.getElementById("status");
    const targetEl = document.getElementById("target");
    const speedValueEl = document.getElementById("speedValue");
    const speedBadgeEl = document.getElementById("speedBadge");
    const speedSliderEl = document.getElementById("speedSlider");
    const speedDecreaseEl = document.getElementById("speedDecrease");
    const speedIncreaseEl = document.getElementById("speedIncrease");
    const presetButtons = [...document.querySelectorAll("button[data-speed-preset]")];
    const buttons = [...document.querySelectorAll("button[data-command]")];
    const activeByKey = new Map();
    const holdDelayMs = 120;
    const speedSyncDelayMs = 120;
    const speedState = {
      value: __DEFAULT_SPEED__,
      min: __MIN_SPEED__,
      max: __MAX_SPEED__,
      step: __SPEED_STEP__,
    };

    let speedSyncTimer = null;

    const commandLabels = {
      forward: "Forward",
      backward: "Backward",
      left: "Left",
      right: "Right",
      stop: "Stop",
    };

    function setActive(command, isActive) {
      buttons
        .filter((button) => button.dataset.command === command)
        .forEach((button) => button.classList.toggle("active", isActive));
    }

    async function sendCommand(command) {
      statusEl.textContent = commandLabels[command] || command;
      try {
        const response = await fetch(`/api/move?command=${encodeURIComponent(command)}`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
      } catch (error) {
        statusEl.textContent = `Error: ${error.message}`;
      }
    }

    function clampSpeed(value) {
      return Math.min(speedState.max, Math.max(speedState.min, value));
    }

    function updateSpeedUi() {
      speedSliderEl.value = String(speedState.value);
      speedValueEl.textContent = String(speedState.value);
      speedBadgeEl.textContent = `PWM ${speedState.value}`;
      presetButtons.forEach((button) => {
        button.classList.toggle("active", Number(button.dataset.speedPreset) === speedState.value);
      });
    }

    async function sendSpeed(value) {
      speedBadgeEl.textContent = `PWM ${value}...`;
      try {
        const response = await fetch(`/api/speed?value=${encodeURIComponent(value)}`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        speedBadgeEl.textContent = `PWM ${value}`;
      } catch (error) {
        speedBadgeEl.textContent = `Error`;
        statusEl.textContent = `Error: ${error.message}`;
      }
    }

    function clearSpeedSyncTimer() {
      if (speedSyncTimer !== null) {
        window.clearTimeout(speedSyncTimer);
        speedSyncTimer = null;
      }
    }

    function scheduleSpeedSync() {
      clearSpeedSyncTimer();
      speedSyncTimer = window.setTimeout(() => {
        speedSyncTimer = null;
        sendSpeed(speedState.value);
      }, speedSyncDelayMs);
    }

    function setSpeed(nextValue, { immediate = false } = {}) {
      const clampedValue = clampSpeed(nextValue);
      speedState.value = clampedValue;
      updateSpeedUi();
      if (immediate) {
        clearSpeedSyncTimer();
        sendSpeed(clampedValue);
      } else {
        scheduleSpeedSync();
      }
    }

    function press(command) {
      setActive(command, true);
      sendCommand(command);
    }

    function release(command, shouldStop = true) {
      setActive(command, false);
      if (shouldStop) {
        sendCommand("stop");
      }
    }

    buttons.forEach((button) => {
      const command = button.dataset.command;
      let isPressed = false;
      let holdTimer = null;
      let didStartMove = false;

      function clearHoldTimer() {
        if (holdTimer !== null) {
          window.clearTimeout(holdTimer);
          holdTimer = null;
        }
      }

      function startPress(event) {
        event.preventDefault();
        if (isPressed) {
          return;
        }
        isPressed = true;
        didStartMove = false;
        button.setPointerCapture(event.pointerId);

        if (command === "stop") {
          didStartMove = true;
          press(command);
          return;
        }

        holdTimer = window.setTimeout(() => {
          holdTimer = null;
          if (!isPressed) {
            return;
          }
          didStartMove = true;
          press(command);
        }, holdDelayMs);
      }

      function endPress(event) {
        if (!isPressed) {
          return;
        }
        isPressed = false;
        clearHoldTimer();
        if (button.hasPointerCapture(event.pointerId)) {
          button.releasePointerCapture(event.pointerId);
        }
        release(command, didStartMove || command === "stop");
      }

      button.addEventListener("pointerdown", startPress);
      button.addEventListener("pointerup", endPress);
      button.addEventListener("pointercancel", endPress);
      button.addEventListener("lostpointercapture", () => {
        if (!isPressed) {
          return;
        }
        isPressed = false;
        clearHoldTimer();
        release(command, didStartMove || command === "stop");
      });
    });

    speedSliderEl.addEventListener("input", (event) => {
      setSpeed(Number(event.target.value));
    });

    speedSliderEl.addEventListener("change", (event) => {
      setSpeed(Number(event.target.value), { immediate: true });
    });

    speedDecreaseEl.addEventListener("click", () => {
      setSpeed(speedState.value - speedState.step, { immediate: true });
    });

    speedIncreaseEl.addEventListener("click", () => {
      setSpeed(speedState.value + speedState.step, { immediate: true });
    });

    presetButtons.forEach((button) => {
      button.addEventListener("click", () => {
        setSpeed(Number(button.dataset.speedPreset), { immediate: true });
      });
    });

    const keyToCommand = {
      ArrowUp: "forward",
      ArrowDown: "backward",
      ArrowLeft: "left",
      ArrowRight: "right",
      " ": "stop",
      Spacebar: "stop",
    };

    window.addEventListener("keydown", (event) => {
      const command = keyToCommand[event.key];
      if (!command) {
        return;
      }
      event.preventDefault();
      if (!activeByKey.get(event.key)) {
        activeByKey.set(event.key, true);
        press(command);
      }
    });

    window.addEventListener("keyup", (event) => {
      const command = keyToCommand[event.key];
      if (!command) {
        return;
      }
      event.preventDefault();
      activeByKey.delete(event.key);
      release(command);
    });

    window.addEventListener("blur", () => {
      clearSpeedSyncTimer();
      sendCommand("stop");
    });

    const urlParams = new URLSearchParams(window.location.search);
    const ip = urlParams.get("ip") || "192.168.50.214";
    const port = urlParams.get("port") || "8888";
    targetEl.textContent = `${ip}:${port}`;
    updateSpeedUi();
  </script>
</body>
</html>"""


def send_command(ip: str, port: int, command: str) -> None:
    payload = command.encode("utf-8") + b"\n"
    with socket.create_connection((ip, port), timeout=2) as sock:
        sock.sendall(payload)
        response = sock.recv(1024).decode("utf-8", errors="ignore").strip()
        print(f"ESP32 response: {response}")


class ControllerHandler(BaseHTTPRequestHandler):
    esp32_ip = "192.168.50.214"
    esp32_port = 8888
    speed_min = 0
    speed_max = 255
    speed_step = 5
    default_speed = 160
    speed_command_template = "V{value}"

    @classmethod
    def build_page(cls) -> str:
        span = max(cls.speed_max - cls.speed_min, 1)
        preset_low = cls.speed_min + max(span // 4, 1)
        preset_mid = cls.default_speed
        preset_high = cls.speed_min + max((span * 3) // 4, 1)

        replacements = {
            "__DEFAULT_SPEED__": str(cls.default_speed),
            "__MIN_SPEED__": str(cls.speed_min),
            "__MAX_SPEED__": str(cls.speed_max),
            "__SPEED_STEP__": str(cls.speed_step),
            "__PRESET_LOW__": str(min(cls.speed_max, preset_low)),
            "__PRESET_MID__": str(cls.default_speed),
            "__PRESET_HIGH__": str(min(cls.speed_max, preset_high)),
        }

        page = HTML_PAGE
        for token, value in replacements.items():
            page = page.replace(token, value)
        return page

    @classmethod
    def format_speed_command(cls, value: int) -> str:
        return cls.speed_command_template.format(value=value)

    def _send_text(self, status_code: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_text(200, self.build_page(), "text/html; charset=utf-8")
            return

        if parsed.path == "/api/move":
            params = parse_qs(parsed.query)
            command_name = params.get("command", [""])[0]
            command = COMMAND_MAP.get(command_name)
            if not command:
                self._send_text(400, "Invalid command")
                return

            try:
                send_command(self.esp32_ip, self.esp32_port, command)
            except OSError as error:
                self._send_text(502, f"Failed to reach ESP32: {error}")
                return

            self._send_text(200, command)
            return

        if parsed.path == "/api/speed":
            params = parse_qs(parsed.query)
            raw_value = params.get("value", [""])[0]
            try:
                speed_value = int(raw_value)
            except ValueError:
                self._send_text(400, "Invalid speed value")
                return

            if not self.speed_min <= speed_value <= self.speed_max:
                self._send_text(400, f"Speed must be between {self.speed_min} and {self.speed_max}")
                return

            command = self.format_speed_command(speed_value)
            try:
                send_command(self.esp32_ip, self.esp32_port, command)
            except OSError as error:
                self._send_text(502, f"Failed to reach ESP32: {error}")
                return

            self._send_text(200, command)
            return

        if parsed.path == "/health":
            self._send_text(200, "ok")
            return

        self._send_text(404, "Not found")

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a browser-based controller for the ESP32 car")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address for the web server")
    parser.add_argument("--port", type=int, default=8000, help="Web server port")
    parser.add_argument("--ip", default="192.168.50.214", help="ESP32 IP address")
    parser.add_argument("--esp32-port", type=int, default=8888, help="ESP32 TCP port")
    parser.add_argument("--default-speed", type=int, default=160, help="Initial speed shown on the web speed panel")
    parser.add_argument("--min-speed", type=int, default=0, help="Minimum speed value accepted by the web API")
    parser.add_argument("--max-speed", type=int, default=255, help="Maximum speed value accepted by the web API")
    parser.add_argument("--speed-step", type=int, default=5, help="Step size for the web speed controls")
    parser.add_argument(
        "--speed-command-template",
        default="V{value}",
        help="Speed command format sent to the ESP32, for example V{value} or SPEED:{value}",
    )
    args = parser.parse_args()

    if args.min_speed > args.max_speed:
        parser.error("--min-speed must be less than or equal to --max-speed")
    if args.speed_step <= 0:
        parser.error("--speed-step must be greater than 0")
    if not args.min_speed <= args.default_speed <= args.max_speed:
        parser.error("--default-speed must be within the min/max speed range")
    if "{value}" not in args.speed_command_template:
        parser.error("--speed-command-template must contain {value}")

    ControllerHandler.esp32_ip = args.ip
    ControllerHandler.esp32_port = args.esp32_port
    ControllerHandler.speed_min = args.min_speed
    ControllerHandler.speed_max = args.max_speed
    ControllerHandler.speed_step = args.speed_step
    ControllerHandler.default_speed = args.default_speed
    ControllerHandler.speed_command_template = args.speed_command_template

    server = ThreadingHTTPServer((args.host, args.port), ControllerHandler)
    print(f"Open http://127.0.0.1:{args.port} in your browser")
    print(f"Forwarding commands to {args.ip}:{args.esp32_port}")
    print(
        "Speed panel range: "
        f"{args.min_speed}-{args.max_speed}, step {args.speed_step}, command template {args.speed_command_template}"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
