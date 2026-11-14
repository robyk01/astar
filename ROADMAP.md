# ASTAR — Engineering Roadmap
**Autonomous Surface Traversal & Astronaut Routing**  
**Target Site:** Jezero Crater, Mars (Perseverance Landing Site)

---

## Project Summary
**ASTAR** is an interactive 3D Marswalk EVA Survival & Route Planning system for human exploration in Jezero Crater. It fuses NASA **Mars Trek** elevation models (DEM) and **USGS** geologic units with a terrain-aware **A\* pathfinding engine** that minimizes slope hazards and astronaut life-support consumption ($O_2$ / battery) while maximizing scientific return, paired with **Perseverance Raw Images API** inspection and CV/VLM hazard analysis.

---

## Architecture Overview
- **Frontend (`frontend/`):** React, Vite, Tailwind CSS, Three.js (3D terrain mesh, orbital texture overlay, interactive routing & layer toggles)
- **Backend (`backend/`):** Python, FastAPI, NumPy, SciPy (DEM slope computation, weighted 8-connected $A^*$, EVA survival telemetry, NASA API & CV/VLM integration)
- **Data (`data/`):** Jezero Crater DEM + CTX/HiRISE imagery (Mars Trek), USGS geologic polygons, Perseverance mission waypoints

---

## Technical Milestones

### Phase 1: Data Acquisition & Preprocessing
- [ ] Extract Jezero Crater Digital Elevation Model (DEM) and orbital imagery from **JPL Mars Trek**
- [ ] Parse USGS planetary geologic unit polygons for Jezero Crater (science targets & aeolian hazard zones)
- [ ] Validate **NASA Perseverance Raw Images JSON API** queries for ground-truth waypoint imagery

### Phase 2: Terrain Analysis & Pathfinding Backend
- [ ] `backend/terrain.py`: Load DEM heightmap $H[i,j]$, compute local slope gradients ($\nabla H$), and generate traversability risk masks ($<8^\circ$ safe, $8^\circ\text{--}15^\circ$ caution, $>15^\circ$ hazard)
- [ ] `backend/planner.py`: Implement 8-connected weighted $A^*$ penalizing steep slopes and uphill elevation gain
- [ ] `backend/main.py`: Expose FastAPI endpoints (`/terrain`, `/route`, `/waypoints`) with CORS enabled

### Phase 3: 3D Map Frontend MVP
- [ ] Initialize React + Vite + Tailwind CSS + Three.js workspace in `frontend/`
- [ ] Generate 3D displaced terrain mesh from DEM heightmap with orbital satellite texture mapping
- [ ] Implement interactive OrbitControls and click-to-set Start / Target waypoints
- [ ] Render 3D traverse trajectory over terrain surface and 2D elevation profile chart

### Phase 4: AI Hazard Assessment & EVA Survival Telemetry
- [ ] Fetch ground-truth Perseverance NavCam/Mastcam imagery for selected waypoints
- [ ] Integrate CV terrain hazard segmentation (sand, bedrock, boulders) and VLM geological briefing
- [ ] Implement EVA Survival Telemetry model (traverse distance, estimated walk time, $O_2$ & battery consumption)

### Phase 5: Multi-Layer Overlays & Emergency Routing
- [ ] Add toggleable map layers: Orbital Visual, Slope Risk Heatmap, and USGS Geologic Units
- [ ] Populate real Jezero Crater POIs (*Octavia E. Butler Landing*, *Neretva Vallis*, *Belva Crater*, *Bright Angel*)
- [ ] Implement 1-click **"Emergency Safe Haven Abort"** route back to lander
