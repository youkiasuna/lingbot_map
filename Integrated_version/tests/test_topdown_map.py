from pathlib import Path
import tempfile
import unittest

from Integrated_version.map.build_topdown_map import FREE_VALUE, OCCUPIED_VALUE, make_occupancy_map


class TopdownMapTests(unittest.TestCase):
    def test_occupancy_builder_marks_floor_free_and_obstacle_occupied(self):
        with tempfile.TemporaryDirectory() as temp:
            ply = Path(temp) / "scene.ply"
            ply.write_text(
                "\n".join(
                    (
                        "ply",
                        "format ascii 1.0",
                        "element vertex 3",
                        "property float x",
                        "property float y",
                        "property float z",
                        "end_header",
                        "0 0 0",
                        "1 0 0",
                        "1 0 0.5",
                        "",
                    )
                ),
                encoding="ascii",
            )

            pixels, metadata = make_occupancy_map(
                ply_path=ply,
                up_axis="z",
                meters_per_pixel=1.0,
                padding_m=0.0,
                min_points_per_pixel=1,
                floor_min_points_per_pixel=1,
                floor_side="lower",
                floor_level_arg=0.0,
                floor_thickness=0.05,
                obstacle_min_height=0.1,
                obstacle_max_height=1.0,
                occupied_dilate_pixels=0,
                max_points=None,
            )

        self.assertEqual(pixels, bytes((FREE_VALUE, OCCUPIED_VALUE)))
        self.assertEqual(metadata["input_points"], 3)
        self.assertEqual(metadata["floor_points"], 2)
        self.assertEqual(metadata["obstacle_points"], 1)


if __name__ == "__main__":
    unittest.main()
