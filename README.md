# ASTAR — Autonomous Surface Traversal & Astronaut Routing

**NASA Space Apps Challenge 2026 · Interplanetary Survival Guide: Martian Map**  
Interactive 3D Jezero Crater EVA path planner combining real NASA orbital terrain data, classical computer vision hazard detection, weighted A* routing, simulated PLSS life-support telemetry, and OpenCLIP ground-level terrain classification.

---

## Key Features

1. **Interactive 3D Jezero Crater Terrain (`Three.js`)**
   - Renders a 67k-vertex downsampled elevation mesh from real MRO CTX orbital data.
   - Switchable map layers: **Orbital**, **Slope Risk** (`<8°`, `8°–15°`, `>15°`), and **Surface Hazard** (safe bedrock, sand traps, boulder fields, imminent danger cores).
   - **Orbit** & **First-Person (`78°` FOV)** camera modes with play/pause, progress scrub, and `0.5x–3x` speed control.
2. **Weighted A* Pathfinding & Dual-Route Comparison**
   - 8-connected A* planner enforcing hard `max_slope_deg` cliff constraints and soft surface hazard penalties.
   - **Compare Shortest Path** mode overlays the **Cyan (Safe A\*)** route against the **Orange (Unconstrained Shortest)** baseline with distance and max-slope deltas.
   - One-click **Abort to Hab** emergency return routing.
3. **EVA Life-Support Telemetry**
   - Estimates traversal duration, elevation climb, max slope, $O_2$ consumption, battery draw, and **round-trip feasibility** (`<45%` one-way reserve threshold).
4. **Perseverance Ground Recon (`OpenCLIP ViT-B-32`)**
   - Matches orbital terrain conditions (`Slope`, `Sand`, `Rock`) under the path or destination to visually verified NASA Mars 2020 Perseverance Mastcam-Z photos, scoring terrain hazards via zero-shot CLIP embeddings.

---

## Real NASA Data vs. Model Estimates

| Component | Source / Type | Details |
| :--- | :--- | :--- |
| **Elevation & Slope** | **Real NASA Data** | MRO CTX Jezero Crater Controlled DEM (`1512×1596` float32, `20.0 m/px`, `-2710.7 m` to `-1515.5 m`) |
| **Orbital Texture & Albedo** | **Real NASA Data** | MRO CTX Jezero Crater Controlled Mosaic (`5040×5322` uint8, `6.0 m/px`) |
| **Rover Ground Photos** | **Real NASA Data** | NASA Mars 2020 Perseverance Raw Images RSS API (Mastcam-Z frames) |
| **Surface Hazard Mask** | **Model Estimate (Classical CV)** | `9×9` local standard deviation for boulder roughness (`p50`–`p95`) + dark smooth percentile (`p05`–`p20`) for sand traps (`cv_hazard.py`) |
| **Optimal Route** | **Algorithm (A\*)** | 8-connected weighted A\* with admissible Euclidean heuristic (`planner.py`) |
| **O₂ & Battery Burn** | **Simulated PLSS Model** | Parameterized after NASA xEMU/PLSS specs (`800 g` $O_2$ tank, `1200 Wh` battery, slope-penalized speed) (`telemetry.py`) |
| **Ground Terrain Scores** | **Pretrained AI (OpenCLIP)** | Zero-shot `ViT-B-32` (`laion2b_s34b_b79k`) cosine similarity on matched Perseverance reference frames (`rover_api.py`) |

---

## Algorithms & Resource Formulas

### 1. Classical Orbital CV (`backend/cv_hazard.py`)
- **Boulder Roughness:** Computes local $9 \times 9$ variance via $\sigma^2 = E[X^2] - (E[X])^2$ using `scipy.ndimage.uniform_filter(size=9)`, normalized against `[p50, p95]`.
- **Sand Traps:** Low-albedo (`[p05, p20]`) smooth regolith (`darkness * (1 - boulder_risk)`).
- **Non-linear Hazard Cost:** `5.0 * (sand_risk ** 1.5) + 3.5 * (boulder_risk ** 1.5)` so mild terrain stays passable while severe cores spike in cost.

### 2. Weighted A* (`backend/planner.py`)
- **Hard Constraint:** Any transition exceeding `max_slope_deg` is rejected.
- **Step Cost:** $\text{cost} = d_{\text{horiz}} + \text{slope\_penalty} + \text{hazard\_mask}$.
- **Admissible Heuristic:** Euclidean distance $\times 1.0$, guaranteeing the minimum-cost path under the active constraints.

### 3. Simulated EVA PLSS Telemetry (`backend/telemetry.py`)
- **Speed:** Base `1.1 m/s` penalized by slope angle.
- **Oxygen (`800 g` usable):** Base metabolic rate + climb-effort scaling; flagged unsafe for round-trip if one-way burn $\ge 45\%$ (reserving $10\%$ emergency margin).
- **Battery (`1200 Wh`):** Avionics/thermal baseline + locomotion & uphill draw.

---

## Running Locally & Tests

```bash
# 1. Start the FastAPI server + Three.js frontend
cd backend
../.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
# Open http://127.0.0.1:8000

# 2. Run unit tests (flat diagonal, cliff detour, sealed wall, sand hazard, uphill cost, resource limit)
../.venv/bin/python -m unittest discover -s backend/tests -v
```
