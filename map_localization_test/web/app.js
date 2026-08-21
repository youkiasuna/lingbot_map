const canvas = document.getElementById("mapCanvas");
const ctx = canvas.getContext("2d");

const stateText = document.getElementById("stateText");
const poseText = document.getElementById("poseText");
const goalText = document.getElementById("goalText");
const pathText = document.getElementById("pathText");
const refreshBtn = document.getElementById("refreshBtn");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");

const model = {
  map: null,
  imageCanvas: null,
  pose: null,
  path: null,
  navigation: null,
  goal: null,
  view: { scale: 1, offsetX: 0, offsetY: 0, width: 0, height: 0 },
};

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.message || response.statusText);
  }
  return payload;
}

async function loadMap() {
  const payload = await fetchJson("/api/map");
  model.map = payload.map;
  const pgm = await fetch(model.map.map_url, { cache: "no-store" }).then((r) => r.arrayBuffer());
  model.imageCanvas = parsePgmToCanvas(new Uint8Array(pgm));
}

async function refreshDynamicState() {
  const [pose, path, navigation] = await Promise.all([
    fetchJson("/api/pose"),
    fetchJson("/api/path"),
    fetchJson("/api/navigation"),
  ]);
  model.pose = pose.pose;
  model.path = path.path;
  model.navigation = navigation.navigation;
  if (model.path && model.path.goal) {
    model.goal = { x_m: model.path.goal.x_m, y_m: model.path.goal.y_m };
  }
  render();
}

function parsePgmToCanvas(bytes) {
  const decoder = new TextDecoder("ascii");
  let index = 0;

  function nextToken() {
    while (index < bytes.length) {
      const value = bytes[index];
      if (value === 35) {
        while (index < bytes.length && bytes[index] !== 10) index += 1;
      } else if (value <= 32) {
        index += 1;
      } else {
        break;
      }
    }
    const start = index;
    while (index < bytes.length && bytes[index] > 32) index += 1;
    return decoder.decode(bytes.slice(start, index));
  }

  const magic = nextToken();
  if (magic !== "P5") throw new Error("Expected P5 PGM map.");
  const width = Number(nextToken());
  const height = Number(nextToken());
  const maxValue = Number(nextToken());
  if (maxValue !== 255) throw new Error("Expected 8-bit PGM map.");
  if (bytes[index] <= 32) index += 1;

  const pixels = bytes.slice(index, index + width * height);
  const imageData = new ImageData(width, height);
  for (let i = 0; i < pixels.length; i += 1) {
    const value = pixels[i];
    const out = i * 4;
    if (value <= 100) {
      imageData.data[out] = 32;
      imageData.data[out + 1] = 39;
      imageData.data[out + 2] = 45;
    } else if (value === 205) {
      imageData.data[out] = 174;
      imageData.data[out + 1] = 183;
      imageData.data[out + 2] = 189;
    } else {
      imageData.data[out] = 238;
      imageData.data[out + 1] = 243;
      imageData.data[out + 2] = 241;
    }
    imageData.data[out + 3] = 255;
  }

  const outCanvas = document.createElement("canvas");
  outCanvas.width = width;
  outCanvas.height = height;
  outCanvas.getContext("2d").putImageData(imageData, 0, 0);
  return outCanvas;
}

function fitCanvas() {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(rect.width * ratio));
  const height = Math.max(1, Math.floor(rect.height * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
}

function updateView() {
  if (!model.imageCanvas) return;
  const scale = Math.min(canvas.width / model.imageCanvas.width, canvas.height / model.imageCanvas.height);
  const width = model.imageCanvas.width * scale;
  const height = model.imageCanvas.height * scale;
  model.view = {
    scale,
    width,
    height,
    offsetX: (canvas.width - width) / 2,
    offsetY: (canvas.height - height) / 2,
  };
}

function worldToCanvas(x_m, y_m) {
  const map = model.map;
  const px = (x_m - map.origin_u_m) / map.meters_per_pixel;
  const py = (map.origin_v_m - y_m) / map.meters_per_pixel;
  return {
    x: model.view.offsetX + px * model.view.scale,
    y: model.view.offsetY + py * model.view.scale,
  };
}

function canvasToWorld(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const x = (clientX - rect.left) * ratio;
  const y = (clientY - rect.top) * ratio;
  const px = (x - model.view.offsetX) / model.view.scale;
  const py = (y - model.view.offsetY) / model.view.scale;
  return {
    x_m: model.map.origin_u_m + px * model.map.meters_per_pixel,
    y_m: model.map.origin_v_m - py * model.map.meters_per_pixel,
  };
}

function render() {
  fitCanvas();
  updateView();
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (model.imageCanvas) {
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(model.imageCanvas, model.view.offsetX, model.view.offsetY, model.view.width, model.view.height);
  }

  drawPath();
  drawGoal();
  drawPose();
  updateText();
}

function drawPath() {
  if (!model.path || !model.path.waypoints || model.path.waypoints.length < 2) return;
  ctx.save();
  ctx.strokeStyle = "#e5a600";
  ctx.lineWidth = Math.max(3, 4 * (window.devicePixelRatio || 1));
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.beginPath();
  model.path.waypoints.forEach((point, index) => {
    const screen = worldToCanvas(point.x_m, point.y_m);
    if (index === 0) ctx.moveTo(screen.x, screen.y);
    else ctx.lineTo(screen.x, screen.y);
  });
  ctx.stroke();
  ctx.restore();
}

function drawGoal() {
  if (!model.goal) return;
  const screen = worldToCanvas(model.goal.x_m, model.goal.y_m);
  ctx.save();
  ctx.strokeStyle = "#b33a3a";
  ctx.lineWidth = 3 * (window.devicePixelRatio || 1);
  const radius = 8 * (window.devicePixelRatio || 1);
  ctx.beginPath();
  ctx.moveTo(screen.x - radius, screen.y - radius);
  ctx.lineTo(screen.x + radius, screen.y + radius);
  ctx.moveTo(screen.x + radius, screen.y - radius);
  ctx.lineTo(screen.x - radius, screen.y + radius);
  ctx.stroke();
  ctx.restore();
}

function drawPose() {
  if (!model.pose) return;
  const screen = worldToCanvas(model.pose.x_m, model.pose.y_m);
  const yaw = ((model.pose.yaw_deg || 0) * Math.PI) / 180;
  const size = 14 * (window.devicePixelRatio || 1);
  ctx.save();
  ctx.translate(screen.x, screen.y);
  ctx.rotate(-yaw);
  ctx.fillStyle = "#087f8c";
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2 * (window.devicePixelRatio || 1);
  ctx.beginPath();
  ctx.moveTo(size, 0);
  ctx.lineTo(-size * 0.65, -size * 0.55);
  ctx.lineTo(-size * 0.45, 0);
  ctx.lineTo(-size * 0.65, size * 0.55);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function updateText() {
  if (model.navigation) {
    stateText.textContent = model.navigation.state || "READY";
  } else {
    stateText.textContent = model.map ? "READY" : "Loading";
  }

  poseText.textContent = model.pose
    ? `${model.pose.x_m.toFixed(2)}, ${model.pose.y_m.toFixed(2)}, ${Number(model.pose.yaw_deg || 0).toFixed(0)} deg`
    : "No current_pose.json";

  goalText.textContent = model.goal
    ? `${model.goal.x_m.toFixed(2)}, ${model.goal.y_m.toFixed(2)}`
    : "Click map";

  pathText.textContent = model.path
    ? `${model.path.path_length_m.toFixed(2)} m, ${model.path.waypoint_count} waypoints`
    : "No path";
}

async function planToClick(event) {
  if (!model.map || !model.pose) {
    stateText.textContent = "Pose missing";
    return;
  }
  const goal = canvasToWorld(event.clientX, event.clientY);
  model.goal = goal;
  goalText.textContent = `${goal.x_m.toFixed(2)}, ${goal.y_m.toFixed(2)}`;
  stateText.textContent = "Planning";
  render();
  try {
    const payload = await fetchJson("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal_x_m: goal.x_m, goal_y_m: goal.y_m }),
    });
    model.path = payload.path;
    model.navigation = { state: "GOAL_SELECTED" };
    render();
  } catch (error) {
    stateText.textContent = error.message;
  }
}

async function postNavigation(url) {
  try {
    const payload = await fetchJson(url, { method: "POST" });
    model.navigation = payload.navigation;
    render();
  } catch (error) {
    stateText.textContent = error.message;
  }
}

async function initialize() {
  try {
    await loadMap();
    await refreshDynamicState();
    render();
  } catch (error) {
    stateText.textContent = error.message;
  }
}

canvas.addEventListener("click", planToClick);
refreshBtn.addEventListener("click", refreshDynamicState);
startBtn.addEventListener("click", () => postNavigation("/api/navigation/start"));
stopBtn.addEventListener("click", () => postNavigation("/api/navigation/stop"));
window.addEventListener("resize", render);

setInterval(refreshDynamicState, 1000);
initialize();
