import sys
import unittest
from pathlib import Path

PLANNER_DIR = Path(__file__).resolve().parents[1] / "planner"
sys.path.insert(0, str(PLANNER_DIR))

from grid_navigation import GridMap, astar_pixels, has_line_of_sight, simplify_path


FREE = 254
OCCUPIED = 0


def grid_map(width: int, height: int, pixels: list[int]) -> GridMap:
    return GridMap(
        width=width,
        height=height,
        pixels=bytes(pixels),
        metadata={
            "meters_per_pixel": 1.0,
            "origin_u_m": 0.0,
            "origin_v_m": float(height),
        },
    )


class GridNavigationTest(unittest.TestCase):
    def test_world_to_pixel_does_not_truncate_outside_coordinates_into_map(self) -> None:
        grid = grid_map(3, 3, [FREE] * 9)

        self.assertEqual(grid.world_to_pixel(-0.01, 2.5), (-1, 0))
        self.assertEqual(grid.world_to_pixel(0.5, 3.01), (0, -1))
        with self.assertRaisesRegex(ValueError, "not traversable"):
            astar_pixels(grid, grid.world_to_pixel(-0.01, 2.5), (1, 1))

    def test_line_of_sight_rejects_a_diagonal_corner_cut(self) -> None:
        grid = grid_map(2, 2, [FREE, OCCUPIED, OCCUPIED, FREE])

        self.assertFalse(has_line_of_sight(grid, (0, 0), (1, 1), False))
        with self.assertRaisesRegex(ValueError, "No path"):
            astar_pixels(grid, (0, 0), (1, 1))

    def test_risk_aware_simplification_keeps_the_safe_detour(self) -> None:
        grid = grid_map(5, 3, [FREE] * 15)
        safe_detour = [(0, 1), (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (4, 1)]
        distances = [10.0] * 15
        for x in range(1, 4):
            distances[grid.width + x] = 0.0

        simplified = simplify_path(
            grid,
            safe_detour,
            obstacle_distances=distances,
            safety_radius_m=1.0,
            risk_weight=10.0,
        )

        self.assertNotEqual(simplified, [safe_detour[0], safe_detour[-1]])
        self.assertIn((4, 0), simplified)


if __name__ == "__main__":
    unittest.main()
