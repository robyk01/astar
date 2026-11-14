"""
Terrain loading and slope computation utilities for Jezero Crater DEM & Mosaic.
"""

from pathlib import Path
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEM_PATH = DATA_DIR / "mro ctx jezero dem controlled.tif"
MOSAIC_PATH = DATA_DIR / "mro ctx jezero mosaic controlled.tif"

PIXEL_SCALE_METERS = 20.0  # From GeoTIFF Tag 33550 (20.0 m/px)


def load_dem(path: Path = DEM_PATH) -> np.ndarray:
    """Load the 32-bit float GeoTIFF DEM into a 2D NumPy array (meters)."""
    img = Image.open(path)
    dem = np.array(img, dtype=np.float32)
    return dem


def compute_slope_deg(dem: np.ndarray, pixel_scale: float = PIXEL_SCALE_METERS) -> np.ndarray:
    """
    Compute local terrain slope angle in degrees at every cell using central differences.
    Note: np.gradient returns (dH/drow, dH/dcol) = (dH/dy, dH/dx).
    """
    grad_y, grad_x = np.gradient(dem, pixel_scale)
    gradient_mag = np.hypot(grad_x, grad_y)
    slope_deg = np.degrees(np.arctan(gradient_mag))
    return slope_deg.astype(np.float32)


def save_previews(dem: np.ndarray, slope_deg: np.ndarray, out_dir: Path = DATA_DIR) -> None:
    """Export normalized grayscale heightmap & RGB slope hazard map PNGs for inspection."""
    
    # Normalized heightmap (0 = lowest floor, 255 = highest rim)
    h_min, h_max = float(dem.min()), float(dem.max())
    norm_h = ((dem - h_min) / (h_max - h_min) * 255.0).clip(0, 255).astype(np.uint8)
    Image.fromarray(norm_h, mode="L").save(out_dir / "preview_heightmap.png")

    # Color-coded slope risk map: Green (<8°), Yellow (8-15°), Red (>15°)
    rgb = np.zeros((*slope_deg.shape, 3), dtype=np.uint8)
    safe = slope_deg < 8.0
    caution = (slope_deg >= 8.0) & (slope_deg < 15.0)
    hazard = slope_deg >= 15.0

    rgb[safe] = [46, 204, 113]      # Green
    rgb[caution] = [241, 196, 15]   # Yellow
    rgb[hazard] = [231, 76, 60]     # Red
    Image.fromarray(rgb, mode="RGB").save(out_dir / "preview_slope_risk.png")


if __name__ == "__main__":
    dem = load_dem()
    slope = compute_slope_deg(dem)
    save_previews(dem, slope)

    total = slope.size
    print(f"DEM shape: {dem.shape} | Elevation: {dem.min():.1f}m to {dem.max():.1f}m")
    print(f"Slope range: {slope.min():.2f}° to {slope.max():.2f}° (mean: {slope.mean():.2f}°)")
    print(f"  Safe (<8°):      {100 * np.sum(slope < 8) / total:.1f}%")
    print(f"  Caution (8-15°): {100 * np.sum((slope >= 8) & (slope < 15)) / total:.1f}%")
    print(f"  Hazard (>15°):   {100 * np.sum(slope >= 15) / total:.1f}%")
    print(f"  Cliff (>20°):    {100 * np.sum(slope >= 20) / total:.1f}%")
    print(f"Previews saved to {DATA_DIR}")
