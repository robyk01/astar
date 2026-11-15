"""
FastAPI backend for ASTAR (Autonomous Surface Traversal & Astronaut Routing).
"""

import io
from pathlib import Path
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image

from terrain import load_dem, compute_slope_deg, MOSAIC_PATH, PIXEL_SCALE_METERS
from planner import astar
from telemetry import compute_eva_telemetry
from cv_hazard import compute_hazard_mask
from rover_api import CACHE_DIR as ROVER_CACHE_DIR, inspect_waypoint

Image.MAX_IMAGE_PIXELS = None

app = FastAPI(title="ASTAR Marswalk API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load terrain & CV hazard mask once at startup
DEM = load_dem()
SLOPE_DEG = compute_slope_deg(DEM)
HAZARD_MASK, SAND_RISK, BOULDER_RISK = compute_hazard_mask()
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
    use_cv_hazard: bool = True
    compare_shortest: bool = False


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


@app.get("/api/hazard-texture")
def get_hazard_texture():
    """Return continuous CV hazard heatmap blended with orbital relief."""
    sub_sand = SAND_RISK[::2, ::2]
    sub_boulder = BOULDER_RISK[::2, ::2]

    # Base orbital shading so craters/ridges stay visible underneath
    base_img = Image.open(MOSAIC_PATH).convert("L").resize(
        (sub_sand.shape[1], sub_sand.shape[0]), Image.Resampling.BILINEAR
    )
    base = np.array(base_img, dtype=np.float32) / 255.0
    rgb = np.stack([base * 55, base * 65, base * 82], axis=-1)

    # Moderate caution layers (smooth alpha blend)
    b_alpha = np.clip((sub_boulder - 0.25) / 0.50, 0.0, 0.75)[..., None]
    rgb = rgb * (1 - b_alpha) + np.array([168, 85, 247]) * b_alpha  # Violet boulders

    s_alpha = np.clip((sub_sand - 0.25) / 0.50, 0.0, 0.75)[..., None]
    rgb = rgb * (1 - s_alpha) + np.array([245, 158, 11]) * s_alpha  # Amber sand

    # Imminent / Severe danger cores (>0.70) -> Deep Crimson
    severe = np.maximum(sub_sand, sub_boulder)
    sev_alpha = np.clip((severe - 0.70) / 0.25, 0.0, 0.90)[..., None]
    rgb = rgb * (1 - sev_alpha) + np.array([220, 38, 38]) * sev_alpha

    # Re-apply subtle orbital relief shading
    shade = (0.65 + 0.35 * base)[..., None]
    out = np.clip(rgb * shade, 0, 255).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(out, mode="RGB").save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


def _classify_cell(r: int, c: int) -> str:
    slope_val = float(SLOPE_DEG[r, c])
    sand_val = float(SAND_RISK[r, c])
    boulder_val = float(BOULDER_RISK[r, c])
    if slope_val >= 11.0:
        return "scarp"
    if sand_val >= 0.35 and sand_val >= boulder_val:
        return "sand"
    if boulder_val >= 0.35:
        return "boulders"
    return "bedrock"


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
        hazard_mask=HAZARD_MASK if req.use_cv_hazard else None,
        max_slope_deg=req.max_slope_deg,
    )
    if not path:
        raise HTTPException(status_code=404, detail="No safe route found under slope constraint")

    elevations = [round(float(DEM[r, c]), 2) for r, c in path]
    terrain_classes = [_classify_cell(r, c) for r, c in path]
    telemetry = compute_eva_telemetry(path, DEM, pixel_scale=PIXEL_SCALE_METERS)

    baseline = None
    if req.compare_shortest:
        base_path = astar(
            DEM,
            (req.start_row, req.start_col),
            (req.goal_row, req.goal_col),
            hazard_mask=None,
            max_slope_deg=45.0,
        )
        if base_path:
            base_elevs = [round(float(DEM[r, c]), 2) for r, c in base_path]
            base_tel = compute_eva_telemetry(base_path, DEM, pixel_scale=PIXEL_SCALE_METERS)
            baseline = {
                "path": base_path,
                "elevations": base_elevs,
                "telemetry": base_tel,
            }

    return {
        "steps": len(path),
        "path": path,
        "elevations": elevations,
        "terrain_classes": terrain_classes,
        "telemetry": telemetry,
        "baseline": baseline,
    }


@app.get("/api/waypoint-inspect")
def api_waypoint_inspect(waypoint_id: str | None = None, row: int = 580, col: int = 620):
    r = max(0, min(ROWS - 1, row))
    c = max(0, min(COLS - 1, col))
    slope_val = float(SLOPE_DEG[r, c])
    sand_val = float(SAND_RISK[r, c])
    boulder_val = float(BOULDER_RISK[r, c])
    terrain_class = _classify_cell(r, c)

    try:
        return inspect_waypoint(
            waypoint_id=waypoint_id,
            row=r,
            col=c,
            terrain_class=terrain_class,
            slope_deg=slope_val,
            sand_risk=sand_val,
            boulder_risk=boulder_val,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Rover inspection failed: {exc}")


@app.get("/api/rover-image/{filename}")
def api_rover_image(filename: str):
    safe_name = Path(filename).name
    img_path = ROVER_CACHE_DIR / safe_name
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Rover image not found")
    return FileResponse(img_path, media_type="image/jpeg")


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
