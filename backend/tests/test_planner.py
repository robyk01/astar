"""
Unit tests for A* pathfinding and EVA survival telemetry.
"""

import sys
from pathlib import Path
import unittest
import numpy as np

# Ensure backend/ modules are importable regardless of working directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from planner import astar
from telemetry import compute_eva_telemetry


class TestPlannerAndTelemetry(unittest.TestCase):
    def test1_flat_diagonal(self):
        """On a flat 5x5 grid, A* should take the shortest straight diagonal."""
        dem = np.zeros((5, 5), dtype=np.float32)
        path = astar(dem, (0, 0), (4, 4))
        print(f"\n  [Flat Diagonal] path={path}")
        self.assertEqual(path, [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)])
        print('\n')

    def test2_cliff_avoidance(self):
        """A* must route around an impassable 50m cliff wall (>20° slope)."""
        dem = np.zeros((5, 5), dtype=np.float32)
        cliff_cells = [(1, 2), (2, 2), (3, 2)]
        for r, c in cliff_cells:
            dem[r, c] = 50.0

        path = astar(dem, (2, 0), (2, 4), max_slope_deg=20.0)
        print(f"\n  [Cliff Avoidance] detour ({len(path)} steps)={path}")
        self.assertTrue(len(path) > 0, "Expected a detour path around the cliff")
        for cell in cliff_cells:
            self.assertNotIn(cell, path, f"Path stepped onto cliff cell {cell}")
        print('\n')

    def test3_impassable_wall_returns_empty(self):
        """If a cliff completely seals off the goal, A* must return an empty list."""
        dem = np.zeros((5, 5), dtype=np.float32)
        dem[:, 2] = 50.0  # Full vertical cliff across column 2
        path = astar(dem, (2, 0), (2, 4), max_slope_deg=20.0)
        print(f"\n  [Sealed Wall] path={path} (correctly unreachable)")
        self.assertEqual(path, [])
        print('\n')

    def test4_hazard_mask_avoidance(self):
        """On flat ground, A* must route around high-risk surface material (e.g. sand trap)."""
        dem = np.zeros((5, 5), dtype=np.float32)
        hazard = np.zeros((5, 5), dtype=np.float32)
        hazard[2, 2] = 10.0  # Sand trap right in the center

        path = astar(dem, (0, 0), (4, 4), hazard_mask=hazard)
        print(f"\n  [Sand Hazard Avoidance] path={path} (skipped (2, 2))")
        self.assertTrue(len(path) > 0)
        self.assertNotIn((2, 2), path, "Path entered high-hazard sand cell (2, 2)")
        print('\n')

    def test5_telemetry_uphill_costs_more(self):
        """Walking uphill must consume strictly more time, O2, and battery than flat ground."""
        path = [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)]

        flat_dem = np.zeros((5, 5), dtype=np.float32)
        uphill_dem = np.zeros((5, 5), dtype=np.float32)
        for col in range(5):
            uphill_dem[0, col] = col * 5.0  # +5m rise per 20m step (~14° climb)

        flat_stats = compute_eva_telemetry(path, flat_dem)
        uphill_stats = compute_eva_telemetry(path, uphill_dem)

        print(
            f"\n  [Telemetry] Flat:   {flat_stats['duration_min']:.2f} min | "
            f"O2: {flat_stats['o2_used_pct']:.3f}% | Bat: {flat_stats['battery_used_pct']:.3f}%"
        )
        print(
            f"  [Telemetry] Uphill: {uphill_stats['duration_min']:.2f} min | "
            f"O2: {uphill_stats['o2_used_pct']:.3f}% | Bat: {uphill_stats['battery_used_pct']:.3f}% | "
            f"Climb: +{uphill_stats['elevation_gain_m']:.1f}m"
        )

        self.assertGreater(uphill_stats["duration_min"], flat_stats["duration_min"])
        self.assertGreater(uphill_stats["o2_used_pct"], flat_stats["o2_used_pct"])
        self.assertGreater(uphill_stats["battery_used_pct"], flat_stats["battery_used_pct"])
        self.assertAlmostEqual(uphill_stats["elevation_gain_m"], 20.0, places=2)
        print('\n')

    def test6_insufficient_return_resources(self):
        """A long steep traverse (>45% O2 or battery one-way) must flag round_trip_feasible=False."""
        # 500 steps x 20m = ~10 km steep uphill climb (+1.5m per 20m step)
        n_steps = 500
        dem = np.zeros((1, n_steps), dtype=np.float32)
        for col in range(n_steps):
            dem[0, col] = col * 1.5
        path = [(0, c) for c in range(n_steps)]

        stats = compute_eva_telemetry(path, dem)
        print(
            f"\n  [Resource Limit] Dist: {stats['distance_m']/1000:.2f} km | "
            f"O2: {stats['o2_used_pct']:.1f}% | Bat: {stats['battery_used_pct']:.1f}% | "
            f"Round-trip feasible: {stats['round_trip_feasible']}"
        )
        self.assertGreater(stats["o2_used_pct"], 45.0)
        self.assertFalse(stats["round_trip_feasible"])
        print('\n')


if __name__ == "__main__":
    unittest.main(verbosity=2)
