import unittest
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"

from Integrated_version.configs.validate_config import load_json, validate_camera, validate_vehicle


class ConfigurationValidationTests(unittest.TestCase):
    def test_repository_templates_load_and_remain_uncalibrated(self):
        camera = load_json(CONFIG_DIR / "camera.json")
        vehicle = load_json(CONFIG_DIR / "vehicle.json")

        camera_unset = validate_camera(camera)
        vehicle_unset = validate_vehicle(vehicle)

        self.assertTrue(camera_unset)
        self.assertTrue(vehicle_unset)
        self.assertFalse(vehicle["safety"]["motor_output_enabled"])


if __name__ == "__main__":
    unittest.main()
