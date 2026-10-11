import unittest
from pathlib import Path

import numpy as np

from Integrated_version.experiments.localize_query_in_3d_viewer import build_viewer_html


class QueryViewerTest(unittest.TestCase):
    def test_viewer_contains_query_camera_payload(self):
        result = {
            "status": "localized",
            "latency_ms": 12.3,
            "best": {
                "frame_index": 1,
                "match_count": 20,
                "inlier_count": 10,
                "confidence": 0.8,
                "position_xyz": [1.0, 2.0, 3.0],
            },
        }
        html = build_viewer_html(
            mapping_dir=Path("mapping"),
            query_image=Path("query.png"),
            points=np.asarray([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]).tolist(),
            references=[{"frame_index": 0, "position": [0.0, 0.0, 0.0]}],
            result=result,
        )
        self.assertIn("Query Camera Pose", html)
        self.assertIn('"query_camera":[1.0,2.0,3.0]', html)
        self.assertIn('"best_frame":1', html)


if __name__ == "__main__":
    unittest.main()
