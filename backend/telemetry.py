import numpy as np

def compute_eva_telemetry(path: list[tuple[int, int]], dem: np.ndarray, pixel_scale: float = 20.0) -> dict:
    total_dist = 0
    max_slope = 0
    total_climb = 0
    o2 = 0.0
    energy = 0.0
    total_time_sec = 0.0

    for i in range(0, len(path) - 1):
        r1, c1 = path[i][0], path[i][1]
        r2, c2 = path[i + 1][0], path[i + 1][1]

        dist = float(np.hypot(r2 - r1, c2 - c1) * pixel_scale)
        dh = float(dem[r2, c2] - dem[r1, c1])
        theta = float(np.degrees(np.arctan(np.abs(dh) / dist)))

        total_dist += dist
        total_climb += max(0.0, dh)
        max_slope = max(max_slope, theta)

        # astronaut speed and time
        v_base = 1.1
        v = v_base / (1.0 + 2.5 * max(0.0, dh/dist) + 0.02 * theta)
        step_time_sec = dist / v

        total_time_sec += step_time_sec

        # life support burn
        effort = 1.0 + 3.0 * max(0.0, dh / dist) + 0.03 * theta
        o2 += step_time_sec * 0.028 * effort
        energy += (step_time_sec / 3600.0) * 120.0 * (1.0 + 0.5 * (effort - 1.0))

    return {
        'distance_m': total_dist,
        'elevation_gain_m': total_climb,
        'max_slope_deg': max_slope,
        'duration_min': total_time_sec / 60.0,
        'o2_used_pct': o2 / 800 * 100,
        'battery_used_pct': energy / 1200 * 100,
        'round_trip_feasible': True if (o2 / 800 * 100 < 45 and energy / 1200 * 100 < 45) else False
    }

