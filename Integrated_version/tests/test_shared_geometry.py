import unittest

import numpy as np

from Integrated_version.map.geometry import axis_indices, cross, dilate, normalize


class SharedGeometryTests(unittest.TestCase):
    def test_axis_mapping_respects_signed_vertical_axis(self):
        self.assertEqual(axis_indices("-y"), (1, -1.0, [0, 2]))

    def test_mask_dilation_uses_circular_neighborhood(self):
        mask = np.zeros((3, 3), dtype=bool)
        mask[1, 1] = True

        expanded = dilate(mask, 1)

        self.assertEqual(int(expanded.sum()), 5)
        self.assertFalse(expanded[0, 0])

    def test_vector_operations_and_zero_normalization(self):
        self.assertEqual(cross((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), (0.0, 0.0, 1.0))
        self.assertEqual(normalize((0.0, 3.0, 4.0)), (0.0, 0.6, 0.8))
        with self.assertRaises(ValueError):
            normalize((0.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
