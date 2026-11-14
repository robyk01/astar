import { MarsScene } from './scene3d.js';

const container = document.getElementById('canvas-container');
const selectStart = document.getElementById('select-start');
const selectGoal = document.getElementById('select-goal');
const coordStart = document.getElementById('coord-start');
const coordGoal = document.getElementById('coord-goal');
const inputSlope = document.getElementById('input-slope');
const slopeVal = document.getElementById('slope-val');
const statusBox = document.getElementById('status-box');
const telemetryCard = document.getElementById('telemetry-card');

let waypoints = [];
let startPt = null;
let goalPt = null;
let pickMode = null;

const scene = new MarsScene(container, (row, col) => {
  if (!pickMode) return;
  if (pickMode === 'start') {
    startPt = { row, col };
    selectStart.value = 'custom';
    coordStart.textContent = `${row}, ${col}`;
  } else if (pickMode === 'goal') {
    goalPt = { row, col };
    selectGoal.value = 'custom';
    coordGoal.textContent = `${row}, ${col}`;
  }
  pickMode = null;
  document.body.style.cursor = 'default';
  scene.setMarkers(startPt, goalPt);
});

function showStatus(msg, isError = false) {
  statusBox.textContent = msg;
  statusBox.className = `rounded-xl px-3 py-2 text-[11px] ${
    isError ? 'bg-rose-500/15 text-rose-300' : 'bg-white/10 text-white/75'
  }`;
  statusBox.classList.remove('hidden');
}

function drawElevationChart(elevations) {
  const canvas = document.getElementById('elevationChart');
  const ctx = canvas.getContext('2d');
  const w = (canvas.width = canvas.clientWidth * 2);
  const h = (canvas.height = canvas.clientHeight * 2);
  ctx.clearRect(0, 0, w, h);

  if (!elevations || elevations.length < 2) return;
  const minE = Math.min(...elevations);
  const maxE = Math.max(...elevations);
  const span = Math.max(1, maxE - minE);

  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, 'rgba(255, 255, 255, 0.20)');
  grad.addColorStop(1, 'rgba(255, 255, 255, 0.0)');

  ctx.beginPath();
  elevations.forEach((e, i) => {
    const x = (i / (elevations.length - 1)) * w;
    const y = h - 10 - ((e - minE) / span) * (h - 22);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.85)';
  ctx.lineWidth = 2.5;
  ctx.stroke();

  ctx.lineTo(w, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();
}

async function computeRoute() {
  if (!startPt || !goalPt) return;
  showStatus('Computing optimal path...');
  try {
    const res = await fetch('/api/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_row: startPt.row,
        start_col: startPt.col,
        goal_row: goalPt.row,
        goal_col: goalPt.col,
        max_slope_deg: Number(inputSlope.value),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Route calculation failed');

    statusBox.classList.add('hidden');
    scene.renderRoute(data.path, data.elevations);
    drawElevationChart(data.elevations);

    const t = data.telemetry;
    telemetryCard.classList.remove('hidden');
    document.getElementById('tel-dist').textContent = `${(t.distance_m / 1000).toFixed(2)} km`;
    document.getElementById('tel-time').textContent = `${t.duration_min.toFixed(0)} min`;
    document.getElementById('tel-climb').textContent = `+${t.elevation_gain_m.toFixed(0)} m`;
    document.getElementById('tel-slope').textContent = `${t.max_slope_deg.toFixed(1)}°`;

    const o2 = Math.min(100, t.o2_used_pct).toFixed(1);
    const bat = Math.min(100, t.battery_used_pct).toFixed(1);
    document.getElementById('tel-o2').textContent = `${o2}%`;
    document.getElementById('bar-o2').style.width = `${o2}%`;
    document.getElementById('tel-bat').textContent = `${bat}%`;
    document.getElementById('bar-bat').style.width = `${bat}%`;

    const badge = document.getElementById('badge-feasible');
    if (t.round_trip_feasible) {
      badge.textContent = '● Round-Trip Safe';
      badge.className = 'text-[11px] font-medium text-emerald-400';
    } else {
      const reasons = [];
      if (t.o2_used_pct >= 45) reasons.push('O₂ > 45%');
      if (t.battery_used_pct >= 45) reasons.push('Bat > 45%');
      badge.textContent = `● No Return (${reasons.join(', ')})`;
      badge.className = 'text-[11px] font-medium text-rose-400';
    }
  } catch (err) {
    showStatus(err.message, true);
  }
}

async function init() {
  showStatus('Loading Jezero terrain...');
  const [terrainRes, wpRes] = await Promise.all([
    fetch('/api/terrain').then((r) => r.json()),
    fetch('/api/waypoints').then((r) => r.json()),
  ]);

  scene.loadTerrain(terrainRes, '/api/texture');
  waypoints = wpRes.waypoints;
  scene.renderWaypoints(waypoints);

  waypoints.forEach((wp, idx) => {
    selectStart.add(new Option(wp.name, idx));
    selectGoal.add(new Option(wp.name, idx));
  });
  const customOpt1 = new Option('Custom Map Point', 'custom');
  customOpt1.hidden = true;
  const customOpt2 = new Option('Custom Map Point', 'custom');
  customOpt2.hidden = true;
  selectStart.add(customOpt1);
  selectGoal.add(customOpt2);

  selectStart.selectedIndex = 0;
  selectGoal.selectedIndex = 1;
  startPt = { row: waypoints[0].row, col: waypoints[0].col };
  goalPt = { row: waypoints[1].row, col: waypoints[1].col };
  coordStart.textContent = `${startPt.row}, ${startPt.col} · ${waypoints[0].elevation_m} m`;
  coordGoal.textContent = `${goalPt.row}, ${goalPt.col} · ${waypoints[1].elevation_m} m`;
  scene.setMarkers(startPt, goalPt);

  await computeRoute();
}

selectStart.addEventListener('change', () => {
  const wp = waypoints[selectStart.value];
  startPt = { row: wp.row, col: wp.col };
  coordStart.textContent = `${startPt.row}, ${startPt.col} · ${wp.elevation_m} m`;
  scene.setMarkers(startPt, goalPt);
});

selectGoal.addEventListener('change', () => {
  const wp = waypoints[selectGoal.value];
  goalPt = { row: wp.row, col: wp.col };
  coordGoal.textContent = `${goalPt.row}, ${goalPt.col} · ${wp.elevation_m} m`;
  scene.setMarkers(startPt, goalPt);
});

inputSlope.addEventListener('input', () => {
  slopeVal.textContent = `${inputSlope.value}°`;
});

document.getElementById('btn-pick-start').addEventListener('click', () => {
  pickMode = 'start';
  document.body.style.cursor = 'crosshair';
  showStatus('Click terrain to set Origin.');
});

document.getElementById('btn-pick-goal').addEventListener('click', () => {
  pickMode = 'goal';
  document.body.style.cursor = 'crosshair';
  showStatus('Click terrain to set Destination.');
});

document.getElementById('btn-compute').addEventListener('click', computeRoute);

document.getElementById('btn-abort').addEventListener('click', () => {
  const hab = waypoints[0];
  if (goalPt.row === hab.row && goalPt.col === hab.col) {
    showStatus('Destination is already set to Hab.');
    return;
  }
  const prevGoalSelect = selectGoal.value;
  startPt = { ...goalPt };
  goalPt = { row: hab.row, col: hab.col };
  selectStart.value = prevGoalSelect;
  selectGoal.value = '0';
  coordStart.textContent = `${startPt.row}, ${startPt.col}`;
  coordGoal.textContent = `${goalPt.row}, ${goalPt.col} · Hab`;
  scene.setMarkers(startPt, goalPt);
  computeRoute();
});

document.getElementById('btn-reset').addEventListener('click', () => {
  selectStart.value = '0';
  selectGoal.value = '1';
  inputSlope.value = 20;
  slopeVal.textContent = '20°';
  startPt = { row: waypoints[0].row, col: waypoints[0].col };
  goalPt = { row: waypoints[1].row, col: waypoints[1].col };
  coordStart.textContent = `${startPt.row}, ${startPt.col} · ${waypoints[0].elevation_m} m`;
  coordGoal.textContent = `${goalPt.row}, ${goalPt.col} · ${waypoints[1].elevation_m} m`;
  scene.setMarkers(startPt, goalPt);
  computeRoute();
});

const activeTab = 'rounded-full bg-white text-black px-3.5 py-1 text-xs font-medium transition';
const idleTab = 'rounded-full text-white/60 hover:text-white px-3.5 py-1 text-xs font-medium transition';

document.getElementById('btn-layer-orbital').addEventListener('click', () => {
  scene.setTexture('/api/texture');
  document.getElementById('btn-layer-orbital').className = activeTab;
  document.getElementById('btn-layer-slope').className = idleTab;
});

document.getElementById('btn-layer-slope').addEventListener('click', () => {
  scene.setTexture('/api/slope-texture');
  document.getElementById('btn-layer-slope').className = activeTab;
  document.getElementById('btn-layer-orbital').className = idleTab;
});

init();
