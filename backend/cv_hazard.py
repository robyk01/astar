from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter
from terrain import MOSAIC_PATH

Image.MAX_IMAGE_PIXELS = None

def compute_hazard_mask(
    mosaic_path: Path = MOSAIC_PATH,
    target_shape: tuple[int, int] = (1512, 1596),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    img = Image.open(mosaic_path).convert("L").resize((target_shape[1], target_shape[0]), Image.Resampling.BILINEAR)
    albedo = np.array(img, dtype=np.float32) / 255.0

    local_mean = uniform_filter(albedo, size=9) # expected value
    local_sq_mean = uniform_filter(albedo ** 2, size=9) # squared expected
    local_std = np.sqrt(np.maximum(0.0, local_sq_mean - local_mean ** 2)) # standard deviation (sqrt(variance))
    p50, p95 = np.percentile(local_std, [50, 95])
    boulder_risk = np.clip((local_std - p50) / max(1e-6, p95 - p50), 0.0, 1.0)

    a_p05, a_p20 = np.percentile(albedo, [5, 20])
    darkness = np.clip((a_p20 - albedo) / max(1e-6, a_p20 - a_p05), 0.0, 1.0)
    smoothness = 1.0 - boulder_risk
    sand_risk = darkness * smoothness

    # Non-linear severity: mild zones stay passable, imminent cores (>0.75) spike in cost
    hazard_mask = (5.0 * (sand_risk ** 1.5) + 3.5 * (boulder_risk ** 1.5)).astype(np.float32)

    return hazard_mask, sand_risk.astype(np.float32), boulder_risk.astype(np.float32)