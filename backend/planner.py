import math
import heapq
import numpy as np

PIXEL_SCALE = 20.0
DIAG = PIXEL_SCALE * math.sqrt(2)

neighbors = [
    (-1,  0, PIXEL_SCALE), (-1,  1, DIAG),
    ( 0,  1, PIXEL_SCALE), ( 1,  1, DIAG),
    ( 1,  0, PIXEL_SCALE), ( 1, -1, DIAG),
    ( 0, -1, PIXEL_SCALE), (-1, -1, DIAG),
]


def heuristic(r1: int, c1: int, r2: int, c2: int, pixel_scale: float = PIXEL_SCALE) -> float:
    """Returns the admissible straight-line Euclidean distance in meters between (r1, c1) and (r2, c2)."""
    return math.hypot((r2 - r1) * pixel_scale, (c2 - c1) * pixel_scale)


def step_cost(
    dem: np.ndarray,
    r: int,
    c: int,
    nr: int,
    nc: int,
    dist: float,
    hazard_mask: np.ndarray | None = None,
    max_slope_deg: float = 20.0,
) -> float | None:
    """
    Computes Δh = dem[nr, nc] - dem[r, c] and directional slope angle θ.
    Returns None (impassable cliff) if θ > max_slope_deg; otherwise returns weighted step cost.
    """
    delta_h = float(dem[nr, nc] - dem[r, c])
    theta = math.degrees(math.atan2(abs(delta_h), dist))

    if theta > max_slope_deg:
        return None

    slope_penalty = 2.0 * ((theta / max_slope_deg) ** 2)
    climb_penalty = 0.5 * max(0.0, delta_h / dist)
    hazard_penalty = float(hazard_mask[nr, nc]) if hazard_mask is not None else 0.0

    return dist * (1.0 + slope_penalty + climb_penalty + hazard_penalty)


def reconstruct_path(
    came_from_r: np.ndarray,
    came_from_c: np.ndarray,
    goal: tuple[int, int],
) -> list[tuple[int, int]]:
    """Walks backward from goal through parent arrays until -1 (start), returning start -> goal."""
    r, c = goal
    path = []

    while r != -1:
        path.append((int(r), int(c)))
        prev_r = came_from_r[r, c]
        prev_c = came_from_c[r, c]
        r, c = int(prev_r), int(prev_c)

    return path[::-1]


def astar(
    dem: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
    hazard_mask: np.ndarray | None = None,
    max_slope_deg: float = 20.0,
) -> list[tuple[int, int]]:
    """Finds the minimum-cost terrain-aware path from start to goal on the DEM grid."""
    rows, cols = dem.shape
    sr, sc = start
    gr, gc = goal

    g = np.full(dem.shape, np.inf, dtype=np.float64)
    closed = np.zeros(dem.shape, dtype=bool)
    came_from_r = np.full(dem.shape, -1, dtype=np.int32)
    came_from_c = np.full(dem.shape, -1, dtype=np.int32)
    heap = []

    g[sr, sc] = 0.0
    heapq.heappush(heap, (heuristic(sr, sc, gr, gc), sr, sc))

    while heap:
        _, r, c = heapq.heappop(heap)
        if (r, c) == (gr, gc):
            return reconstruct_path(came_from_r, came_from_c, goal)

        if closed[r, c]:
            continue
        closed[r, c] = True

        for dr, dc, dist in neighbors:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols) or closed[nr, nc]:
                continue

            cost = step_cost(dem, r, c, nr, nc, dist, hazard_mask, max_slope_deg)
            if cost is None:
                continue

            temp_g = g[r, c] + cost
            if temp_g < g[nr, nc]:
                g[nr, nc] = temp_g
                came_from_r[nr, nc] = r
                came_from_c[nr, nc] = c
                f = temp_g + heuristic(nr, nc, gr, gc)
                heapq.heappush(heap, (f, nr, nc))

    return []


if __name__ == "__main__":
    import time
    from terrain import load_dem

    dem = load_dem()
    start_pt = (750, 800)
    goal_pt = (500, 500)

    t0 = time.perf_counter()
    path = astar(dem, start_pt, goal_pt)
    dt = time.perf_counter() - t0

    print(f"Path found: {len(path)} steps in {dt:.3f}s")
    if path:
        elevs = [float(dem[r, c]) for r, c in path]
        print(f"Start elev: {elevs[0]:.1f}m -> Goal elev: {elevs[-1]:.1f}m")
