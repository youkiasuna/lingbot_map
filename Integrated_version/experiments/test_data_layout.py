import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import analyze_external_queries as queries
import prepare_frame_split as split
from scan_research_data import classify


class DataLayoutTests(unittest.TestCase):
    def test_scene_inputs_and_frame_links_survive_project_move(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            frame = root / "data/frames/000000.jpg"
            frame.parent.mkdir(parents=True)
            frame.write_bytes(b"original")
            scene = root / "outputs/scenes/example"
            with patch.object(split, "ROOT", root):
                inputs = split.scene_inputs(scene)
                split.write_links([frame], inputs / "mapping_frames")
            self.assertTrue(inputs.is_symlink())
            self.assertEqual(inputs.resolve(), root / "data/scenes/example/inputs")
            moved = root.with_name("relocated")
            root.rename(moved)
            self.assertEqual((moved / "outputs/scenes/example/inputs/mapping_frames/000000.jpg").read_bytes(), b"original")

    def test_scan_keeps_originals_and_leaves_temporary_decision_to_user(self):
        self.assertEqual(classify(Path("data/frames/000000.jpg"))[1], "keep")
        self.assertEqual(classify(Path("models/lingbot-map.pt"))[1], "keep")
        self.assertEqual(classify(Path("outputs/tmp/demo/map.ply"))[1], "review")
        self.assertEqual(classify(Path("Integrated_version/web/demo/index.html"))[0], "code_config_docs")

    def test_query_html_is_opt_in(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "queries").mkdir()
            (root / "queries/image.jpg").write_bytes(b"fixture")
            args = SimpleNamespace(
                scene_dir=root, mapping_dir=root / "mapping", query_dir=root / "queries",
                output_dir=root / "results", pose_file=root / "pose.json", publish_min_confidence=0.35,
                max_features=2000, frame_stride=1, ratio=0.75, top_k=5, min_matches=25,
                min_inliers=12, max_pnp_points=300, reprojection_error_px=5.0, pnp_iterations=200,
                max_viewer_points=10, write_viewers=False,
            )
            result = {"status": "lost", "best": None}
            with patch.object(queries, "parse_args", return_value=args), \
                 patch.object(queries, "OrbKeyframeLocalizer") as localizer, \
                 patch.object(queries, "FilePosePublisher"), \
                 patch.object(queries, "load_archive", return_value=Mock()) as load, \
                 patch.object(queries, "sample_world_points", return_value=[]), \
                 patch.object(queries, "camera_centers", return_value=[]), \
                 patch.object(queries, "build_viewer_html", return_value="<html></html>"):
                localizer.return_value.localize.return_value = result
                queries.main()
                load.assert_not_called()
                self.assertFalse(list((root / "results").glob("*.html")))
                summary = json.loads((root / "results/summary.json").read_text())
                self.assertIsNone(summary["records"][0]["viewer_html"])
                args.write_viewers = True
                queries.main()
                self.assertEqual(len(list((root / "results").glob("*.html"))), 1)


if __name__ == "__main__":
    unittest.main()
