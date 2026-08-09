from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MobileDependencySecurityTests(unittest.TestCase):
    def test_js_yaml_three_x_is_patched(self) -> None:
        lock = json.loads(
            (ROOT / "mobile" / "package-lock.json").read_text(encoding="utf-8")
        )
        versions = [
            package["version"]
            for path, package in lock["packages"].items()
            if path.endswith("node_modules/js-yaml")
        ]

        self.assertTrue(versions)
        for version in versions:
            major, minor, patch = (int(part) for part in version.split(".")[:3])
            if major == 3:
                self.assertGreaterEqual((major, minor, patch), (3, 15, 1))


if __name__ == "__main__":
    unittest.main()
