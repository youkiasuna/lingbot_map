const viewer = document.getElementById("viewer");
const stateText = document.getElementById("stateText");
const refreshBtn = document.getElementById("refreshBtn");
const modeText = document.getElementById("modeText");
const versionText = document.getElementById("versionText");
const pointsText = document.getElementById("pointsText");
const windowsText = document.getElementById("windowsText");
const framesText = document.getElementById("framesText");
const windowText = document.getElementById("windowText");
const errorText = document.getElementById("errorText");

let scene;
let camera;
let renderer;
let pointCloud;
let poseMarker;
let yaw = 0.7;
let pitch = 0.45;
let distance = 6;
let dragging = false;
let lastX = 0;
let lastY = 0;

async function getJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || response.statusText);
  return payload;
}

function initViewer() {
  if (!window.THREE) {
    stateText.textContent = "Three.js 載入失敗";
    return;
  }
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x101820);
  camera = new THREE.PerspectiveCamera(55, 1, 0.01, 10000);
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  viewer.appendChild(renderer.domElement);
  scene.add(new THREE.GridHelper(10, 20, 0x4a6872, 0x26383e));
  scene.add(new THREE.AxesHelper(1));
  poseMarker = new THREE.Mesh(
    new THREE.SphereGeometry(0.08, 16, 12),
    new THREE.MeshBasicMaterial({ color: 0xff5533 })
  );
  poseMarker.visible = false;
  scene.add(poseMarker);
  resize();
  viewer.addEventListener("pointerdown", (event) => {
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    viewer.setPointerCapture(event.pointerId);
  });
  viewer.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    yaw -= (event.clientX - lastX) * 0.008;
    pitch = Math.max(-1.4, Math.min(1.4, pitch + (event.clientY - lastY) * 0.008));
    lastX = event.clientX;
    lastY = event.clientY;
  });
  viewer.addEventListener("pointerup", () => { dragging = false; });
  viewer.addEventListener("wheel", (event) => {
    distance = Math.max(0.3, Math.min(100, distance * Math.exp(event.deltaY * 0.001)));
    event.preventDefault();
  }, { passive: false });
  animate();
}

function resize() {
  if (!renderer) return;
  const width = Math.max(1, viewer.clientWidth);
  const height = Math.max(1, viewer.clientHeight);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function replacePointCloud(points, rgbColors = []) {
  if (!scene || !window.THREE) return;
  if (pointCloud) {
    scene.remove(pointCloud);
    pointCloud.geometry.dispose();
    pointCloud.material.dispose();
  }
  if (!points.length) {
    pointCloud = null;
    return;
  }
  const positions = new Float32Array(points.length * 3);
  const colors = new Float32Array(points.length * 3);
  let minX = Infinity, maxX = -Infinity;
  let minY = Infinity, maxY = -Infinity;
  let minZ = Infinity, maxZ = -Infinity;
  points.forEach((p) => {
    minX = Math.min(minX, p[0]); maxX = Math.max(maxX, p[0]);
    minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]);
    minZ = Math.min(minZ, p[2]); maxZ = Math.max(maxZ, p[2]);
  });
  const center = [(minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2];
  const span = Math.max(maxX - minX, maxY - minY, maxZ - minZ, 0.1);
  points.forEach((p, i) => {
    positions.set([(p[0] - center[0]), (p[1] - center[1]), (p[2] - center[2])], i * 3);
    const height = (p[1] - minY) / span;
    if (rgbColors.length === points.length && rgbColors[i] && rgbColors[i].length >= 3) {
      colors.set([
        rgbColors[i][0] / 255,
        rgbColors[i][1] / 255,
        rgbColors[i][2] / 255,
      ], i * 3);
    } else {
      colors.set([0.1 + height * 0.2, 0.65 + height * 0.25, 0.85], i * 3);
    }
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  pointCloud = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({ size: Math.max(span / 300, 0.005), vertexColors: true })
  );
  pointCloud.position.set(center[0], center[1], center[2]);
  scene.add(pointCloud);
  distance = Math.max(span * 1.8, 1);
}

function updatePoseMarker(posePayload) {
  if (!poseMarker) return;
  const position = posePayload && posePayload.position_xyz;
  const status = String((posePayload && posePayload.status) || "").toLowerCase();
  const timestamp = Number(posePayload && posePayload.timestamp_unix);
  const age = Number.isFinite(timestamp) ? (Date.now() / 1000) - timestamp : Infinity;
  const invalidStatuses = new Set(["lost", "low_confidence", "rejected", "stale", "missing"]);
  const valid = Array.isArray(position)
    && position.length >= 3
    && position.slice(0, 3).every(Number.isFinite)
    && !invalidStatuses.has(status)
    && age >= -5
    && age <= 10;
  poseMarker.visible = valid;
  if (valid) {
    poseMarker.position.set(position[0], position[1], position[2]);
  }
}

function animate() {
  requestAnimationFrame(animate);
  if (!renderer) return;
  const target = pointCloud ? pointCloud.position : new THREE.Vector3();
  const horizontal = Math.cos(pitch) * distance;
  camera.position.set(
    target.x + Math.sin(yaw) * horizontal,
    target.y + Math.sin(pitch) * distance,
    target.z + Math.cos(yaw) * horizontal
  );
  camera.lookAt(target);
  renderer.render(scene, camera);
}

function showStatus(status, map, pointcloudRecord, statusRecord) {
  const quality = map && map.quality ? map.quality : {};
  const mapRecord = pointcloudRecord || (map && map.record) || {};
  const liveRecord = statusRecord || (status && status.record) || {};
  modeText.textContent = liveRecord.mode || status.mode || "等待";
  versionText.textContent = mapRecord.map_version ?? map?.map_version ?? "-";
  pointsText.textContent = mapRecord.point_count ?? quality.point_count ?? "-";
  windowsText.textContent = status.processed_windows ?? "-";
  framesText.textContent = status.submitted_frames ?? "-";
  windowText.textContent = status.mapping_window_id ?? "-";
  errorText.textContent = status.worker_error || status.reader_error || "無";
  stateText.textContent = liveRecord.mode === "MAPPING" ? "即時建圖中" : "等待資料";
}

async function refresh() {
  try {
    const [statusResponse, mapResponse, poseResponse] = await Promise.all([
      getJson("/api/live/status"),
      getJson("/api/live/map"),
      getJson("/api/live/pose"),
    ]);
    const status = statusResponse.status || {};
    showStatus(
      status,
      mapResponse.map,
      mapResponse.pointcloud_record,
      mapResponse.status_record
    );
    replacePointCloud(mapResponse.points_xyz || [], mapResponse.colors_rgb || []);
    updatePoseMarker(poseResponse.pose || null);
  } catch (error) {
    stateText.textContent = "等待 live mapping";
    errorText.textContent = error.message;
  }
}

refreshBtn.addEventListener("click", refresh);
window.addEventListener("resize", resize);
initViewer();
refresh();
setInterval(refresh, 1000);
