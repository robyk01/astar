import { MarsScene } from './scene3d.js?v=8';

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
let lastRoutePath = [];
let lastFpvBucket = -1;
let inspectSeq = 0;

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
        use_cv_hazard: document.getElementById('toggle-cv').checked,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Route calculation failed');

    statusBox.classList.add('hidden');
    lastRoutePath = data.path;
    lastFpvBucket = -1;
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

const legendBox = document.getElementById('layer-legend');
const legendItems = document.getElementById('legend-items');

const LEGENDS = {
  'btn-layer-orbital': null,
  'btn-layer-slope': [
    { color: '#2ecc71', label: '< 8° Safe' },
    { color: '#f1c40f', label: '8°–15° Caution' },
    { color: '#e74c3c', label: '> 15° Hazard' },
  ],
  'btn-layer-cv': [
    { color: '#dc2626', label: 'Imminent Danger' },
    { color: '#f59e0b', label: 'Sand Trap' },
    { color: '#a855f7', label: 'Boulder / Rough' },
    { color: '#262e3d', label: 'Safe Bedrock' },
  ],
};

function setLayerTab(activeId, textureUrl) {
  scene.setTexture(textureUrl);
  ['btn-layer-orbital', 'btn-layer-slope', 'btn-layer-cv'].forEach((id) => {
    document.getElementById(id).className = id === activeId ? activeTab : idleTab;
  });

  const items = LEGENDS[activeId];
  if (!items) {
    legendBox.classList.add('hidden');
  } else {
    legendItems.innerHTML = items
      .map(
        (it) =>
          `<span class="inline-flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full" style="background:${it.color}"></span><span>${it.label}</span></span>`
      )
      .join('');
    legendBox.classList.remove('hidden');
  }
}

document.getElementById('btn-layer-orbital').addEventListener('click', () => setLayerTab('btn-layer-orbital', '/api/texture'));
document.getElementById('btn-layer-slope').addEventListener('click', () => setLayerTab('btn-layer-slope', '/api/slope-texture'));
document.getElementById('btn-layer-cv').addEventListener('click', () => setLayerTab('btn-layer-cv', '/api/hazard-texture'));
document.getElementById('toggle-cv').addEventListener('change', computeRoute);

// --- Camera Mode (Orbit vs First-Person Traverse) ---
const btnCamOrbit = document.getElementById('btn-cam-orbit');
const btnCamFpv = document.getElementById('btn-cam-fpv');
const fpvBar = document.getElementById('fpv-bar');
const btnFpvPlay = document.getElementById('btn-fpv-play');
const inputFpvProgress = document.getElementById('input-fpv-progress');
const fpvPct = document.getElementById('fpv-pct');

const activeCamTab = 'rounded-full bg-white text-black px-3 py-1 text-xs font-medium transition';
const idleCamTab = 'rounded-full text-white/60 hover:text-white px-3 py-1 text-xs font-medium transition';

async function setCameraUI(mode) {
  if (mode === 'fpv') {
    if (!scene.routeCurve) {
      await computeRoute();
    }
    if (!scene.routeCurve) return;
    btnCamOrbit.className = idleCamTab;
    btnCamFpv.className = activeCamTab;
    fpvBar.classList.remove('hidden');
    btnFpvPlay.textContent = 'Pause';
    scene.setCameraMode(mode);
    syncFpvCheckpoint(scene.fpvProgress, true);
  } else {
    btnCamOrbit.className = activeCamTab;
    btnCamFpv.className = idleCamTab;
    fpvBar.classList.add('hidden');
    scene.setCameraMode(mode);
  }
}

btnCamOrbit.addEventListener('click', () => setCameraUI('orbit'));
btnCamFpv.addEventListener('click', () => setCameraUI('fpv'));

btnFpvPlay.addEventListener('click', (e) => {
  e.stopPropagation();
  const next = !scene.fpvPlaying;
  if (next && scene.fpvProgress >= 0.99) scene.setFpvProgress(0);
  scene.setFpvPlaying(next);
  btnFpvPlay.textContent = next ? 'Pause' : 'Play';
});

inputFpvProgress.addEventListener('input', () => {
  scene.setFpvPlaying(false);
  btnFpvPlay.textContent = 'Play';
  const t = Number(inputFpvProgress.value) / 100;
  scene.setFpvProgress(t);
  fpvPct.textContent = `${inputFpvProgress.value}%`;
  syncFpvCheckpoint(t, false);
});

scene.onFpvProgress = (t, playing) => {
  const pct = Math.round(t * 100);
  if (inputFpvProgress.value !== String(pct)) {
    inputFpvProgress.value = pct;
  }
  const pctStr = `${pct}%`;
  if (fpvPct.textContent !== pctStr) {
    fpvPct.textContent = pctStr;
  }
  const playLabel = playing ? 'Pause' : 'Play';
  if (btnFpvPlay.textContent !== playLabel) {
    btnFpvPlay.textContent = playLabel;
  }
  syncFpvCheckpoint(t, false);
};

// --- NASA Perseverance + CLIP Ground Inspection ---
const inspectCard = document.getElementById('inspect-card');
const inspectMeta = document.getElementById('inspect-meta');
const inspectImg = document.getElementById('inspect-img');
const inspectTopClass = document.getElementById('inspect-top-class');
const inspectRiskBadge = document.getElementById('inspect-risk-badge');
const inspectAdvisory = document.getElementById('inspect-advisory');
const inspectBars = document.getElementById('inspect-bars');

document.getElementById('btn-inspect-close').addEventListener('click', () => {
  inspectCard.classList.add('hidden');
});

async function inspectCoord(row, col, wpId = '', checkpointLabel = '') {
  const seq = ++inspectSeq;
  inspectCard.classList.remove('hidden');
  inspectMeta.textContent = checkpointLabel
    ? `${checkpointLabel} · Fetching NASA Perseverance...`
    : 'Fetching NASA Perseverance & classifying...';

  const qs = new URLSearchParams({ row: String(row), col: String(col) });
  if (wpId) qs.set('waypoint_id', wpId);

  try {
    const res = await fetch(`/api/waypoint-inspect?${qs.toString()}`);
    const data = await res.json();
    if (seq !== inspectSeq) return; // Ignore stale out-of-order response
    if (!res.ok) throw new Error(data.detail || 'Inspection failed');

    if (inspectImg.getAttribute('src') !== data.image_url) {
      const pre = new Image();
      pre.onload = () => {
        if (seq !== inspectSeq) return;
        inspectImg.style.opacity = '0';
        setTimeout(() => {
          if (seq !== inspectSeq) return;
          inspectImg.src = data.image_url;
          inspectImg.style.opacity = '1';
        }, 160);
      };
      pre.src = data.image_url;
    }

    const prefix = checkpointLabel ? `${checkpointLabel} · ` : '';
    inspectMeta.textContent = `${prefix}Sol ${data.sol ?? '?'} · ${data.camera}`;
    inspectTopClass.textContent = data.top_class;
    inspectRiskBadge.textContent = data.top_risk;
    inspectAdvisory.textContent = data.advisory;

    const barColors = {
      bedrock: 'bg-emerald-400',
      sand: 'bg-amber-400',
      boulders: 'bg-purple-400',
      scarp: 'bg-rose-400',
    };

    if (!inspectBars.children.length) {
      inspectBars.innerHTML = data.scores
        .map((s) => {
          const pct = Math.round(s.probability * 100);
          const color = barColors[s.id] || 'bg-white';
          return `
            <div data-cls="${s.id}">
              <div class="flex justify-between text-[10px] mb-1">
                <span class="cls-label text-white/75">${s.label}</span>
                <span class="cls-pct tabular text-white/60">${pct}%</span>
              </div>
              <div class="h-[3px] w-full rounded-full bg-white/10 overflow-hidden">
                <div class="cls-bar h-full ${color} transition-all duration-500 ease-out" style="width:${pct}%"></div>
              </div>
            </div>
          `;
        })
        .join('');
    } else {
      data.scores.forEach((s) => {
        const rowEl = inspectBars.querySelector(`[data-cls="${s.id}"]`);
        if (!rowEl) return;
        const pct = Math.round(s.probability * 100);
        rowEl.querySelector('.cls-pct').textContent = `${pct}%`;
        rowEl.querySelector('.cls-bar').style.width = `${pct}%`;
      });
    }
  } catch (err) {
    if (seq === inspectSeq) inspectMeta.textContent = err.message;
  }
}

function syncFpvCheckpoint(t, force = false) {
  if (!lastRoutePath || lastRoutePath.length === 0) return;
  const bucket = Math.min(4, Math.floor(t * 5));
  if (!force && bucket === lastFpvBucket) return;
  lastFpvBucket = bucket;
  const idx = Math.min(
    lastRoutePath.length - 1,
    Math.round((bucket / 4) * (lastRoutePath.length - 1))
  );
  const [r, c] = lastRoutePath[idx];
  const pctLabels = ['0%', '25%', '50%', '75%', '100%'];
  inspectCoord(r, c, '', `Traverse ${pctLabels[bucket]}`);
}

document.getElementById('btn-inspect').addEventListener('click', () => {
  if (!goalPt) return;
  const wpIdx = selectGoal.value;
  const wpId = wpIdx !== 'custom' && waypoints[Number(wpIdx)] ? waypoints[Number(wpIdx)].id : '';
  inspectCoord(goalPt.row, goalPt.col, wpId);
});

init();
