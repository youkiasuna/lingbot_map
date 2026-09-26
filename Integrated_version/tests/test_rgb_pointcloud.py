from __future__ import annotations

import unittest

import numpy as np
import torch

from runtime.rgb_pointcloud import flatten_colored_world_points
from runtime.lingbot_map_session import images_tensor_to_rgb_uint8


class RGBPointCloudTests(unittest.TestCase):
    def test_points_and_colors_remain_aligned(self) -> None:
        points = np.array(
            [[[[1.0, 2.0, 3.0], [np.nan, 0.0, 0.0]]]],
            dtype=np.float32,
        )
        images = np.array([[[[10, 20, 30], [40, 50, 60]]]], dtype=np.uint8)

        output_points, output_colors = flatten_colored_world_points(points, images)

        np.testing.assert_array_equal(output_points, [[1.0, 2.0, 3.0]])
        np.testing.assert_array_equal(output_colors, [[10, 20, 30]])

    def test_shape_mismatch_is_rejected(self) -> None:
        points = np.zeros((1, 2, 2, 3), dtype=np.float32)
        images = np.zeros((1, 2, 3, 3), dtype=np.uint8)
        with self.assertRaises(ValueError):
            flatten_colored_world_points(points, images)

    def test_max_points_keeps_matching_colors(self) -> None:
        points = np.arange(30, dtype=np.float32).reshape(1, 10, 1, 3)
        images = np.arange(30, dtype=np.uint8).reshape(1, 10, 1, 3)

        output_points, output_colors = flatten_colored_world_points(
            points, images, max_points=5
        )

        self.assertEqual(len(output_points), len(output_colors))
        self.assertLessEqual(len(output_points), 5)

    def test_session_rgb_extraction_accepts_batched_5d_tensor(self) -> None:
        images = torch.zeros((1, 2, 3, 1, 2), dtype=torch.float32)
        images[0, 0, :, 0, 0] = torch.tensor([1.0, 0.5, 0.25])

        rgb = images_tensor_to_rgb_uint8(images)

        self.assertEqual(rgb.shape, (2, 1, 2, 3))
        self.assertEqual(rgb.dtype, np.uint8)
        self.assertEqual(rgb[0, 0, 0].tolist(), [255, 127, 63])


if __name__ == "__main__":
    unittest.main()
