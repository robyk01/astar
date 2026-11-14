"""
FastAPI backend for ASTAR (Autonomous Surface Traversal & Astronaut Routing).
"""

import io
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from PIL import Image

from terrain import load_dem, compute_slope_deg, MOSAIC_PATH, PIXEL_SCALE_METERS
from planner import astar
from telemetry import compute_eva_telemetry

Image.MAX_IMAGE_PIXELS = None

app = FastAPI(title="ASTAR Marswalk API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load terrain once at startup
DEM = load_dem()
SLOPE_DEG = compute_slope_deg(DEM)
ROWS, COLS = DEM.shape

# Downsampled grid size for lightweight 3D Three.js mesh
MESH_STRIDE = 6  # 1512/6 = 252 rows, 1596/6 = 266 cols (~67k vertices)

# Canonical Jezero Crater POIs mapped onto the (1512, 1596) grid
WAYPOINTS = [
    {
        "id": "landing",
        "name": "Octavia E. Butler Landing (Hab)",
        "row": 780,
        "col": 840,
        "type": "base",
        "description": "Primary flat basaltic crater floor basecamp.",
    },
    {
        "id": "delta_scarp",
        "name": "Neretva Vallis Delta Scarp",
        "row": 620,
        "col": 580,
        "type": "science",
        "description": "Ancient river delta sedimentary cliffs; high biosignature potential.",
    },
    {
        "id": "belva_crater",
        "name": "Belva Crater Rim",
        "row": 520,
        "col": 680,
        "type": "science",
        "description": "Impact crater exposing deep subsurface bedrock stratigraphy.",
    },
    {
        "id": "bright_angel",
        "name": "Bright Angel Outcrop",
        "row": 480,
        "col": 490,
        "type": "science",
        "description": "Light-toned layered mudstones along the ancient river channel.",
    },
]


class RouteRequest(BaseModel):
    start_row: int
    start_col: int
    goal_row: int
    goal_col: int
    max_slope_deg: float = 20.0


@app.get("/api/health")
def health():
    return {"status": "ok", "dem_shape": [ROWS, COLS]}


@app.get("/api/waypoints")
def get_waypoints():
    enriched = []
    for wp in WAYPOINTS:
        r, c = wp["row"], wp["col"]
        enriched.append({
            **wp,
            "elevation_m": round(float(DEM[r, c]), 2),
            "slope_deg": round(float(SLOPE_DEG[r, c]), 2),
        })
    return {"waypoints": enriched}


@app.get("/api/terrain")
def get_terrain():
    """Return downsampled elevation array + metadata for Three.js 3D mesh generation."""
    sub = DEM[::MESH_STRIDE, ::MESH_STRIDE]
    return {
        "rows": int(sub.shape[0]),
        "cols": int(sub.shape[1]),
        "full_rows": ROWS,
        "full_cols": COLS,
        "stride": MESH_STRIDE,
        "pixel_scale_m": PIXEL_SCALE_METERS,
        "min_elev_m": float(DEM.min()),
        "max_elev_m": float(DEM.max()),
        "heights": np.round(sub, 2).flatten().tolist(),
    }


@app.get("/api/texture")
def get_texture():
    """Return resized orbital CTX mosaic PNG matching the 3D terrain mesh."""
    img = Image.open(MOSAIC_PATH).convert("RGB")
    img_small = img.resize((1024, int(1024 * ROWS / COLS)), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    img_small.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/api/slope-texture")
def get_slope_texture():
    """Return color-coded slope hazard overlay PNG (Green <8°, Yellow 8-15°, Red >15°)."""
    sub_slope = SLOPE_DEG[::2, ::2]
    rgb = np.zeros((*sub_slope.shape, 3), dtype=np.uint8)
    rgb[sub_slope < 8.0] = [46, 204, 113]
    rgb[(sub_slope >= 8.0) & (sub_slope < 15.0)] = [241, 196, 15]
    rgb[sub_slope >= 15.0] = [231, 76, 60]

    buf = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.post("/api/route")
def compute_route(req: RouteRequest):
    for name, r, c in [
        ("start", req.start_row, req.start_col),
        ("goal", req.goal_row, req.goal_col),
    ]:
        if not (0 <= r < ROWS and 0 <= c < COLS):
            raise HTTPException(status_code=400, detail=f"{name} coordinates out of bounds")

    path = astar(
        DEM,
        (req.start_row, req.start_col),
        (req.goal_row, req.goal_col),
        max_slope_deg=req.max_slope_deg,
    )
    if not path:
        raise HTTPException(status_code=404, detail="No safe route found under slope constraint")

    elevations = [round(float(DEM[r, c]), 2) for r, c in path]
    telemetry = compute_eva_telemetry(path, DEM, pixel_scale=PIXEL_SCALE_METERS)

    return {
        "steps": len(path),
        "path": path,
        "elevations": elevations,
        "telemetry": telemetry,
    }
