import math
import unittest

from Integrated_version.experiments.run_live_mapping_replay import peak_rss_mb


class ProcessMetricsTests(unittest.TestCase):
    def test_peak_rss_is_a_positive_finite_megabyte_value(self):
        value = peak_rss_mb()

        self.assertTrue(math.isfinite(value))
        self.assertGreater(value, 0)


if __name__ == "__main__":
    unittest.main()
