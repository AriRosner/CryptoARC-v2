import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MobileReleaseContractTests(unittest.TestCase):
    def test_command_center_android_version_is_bumped(self) -> None:
        app = json.loads((ROOT / "mobile" / "app.json").read_text(encoding="utf-8"))
        build_info = (ROOT / "mobile" / "src" / "buildInfo.ts").read_text(
            encoding="utf-8"
        )

        self.assertEqual(app["expo"]["version"], "2.0.0")
        self.assertGreater(app["expo"]["android"]["versionCode"], 2)
        self.assertEqual(app["expo"]["android"]["package"], "com.cryptoarc.cockpit")
        self.assertIn(app["expo"]["version"], build_info)
        self.assertIn("androidVersionCode: 3", build_info)
        self.assertIn('label: "Operator Command Center"', build_info)
        self.assertIn('date: "2026-07-26"', build_info)
        self.assertIn("} as const;", build_info)

    def test_internal_profile_produces_an_installable_apk(self) -> None:
        eas = json.loads((ROOT / "mobile" / "eas.json").read_text(encoding="utf-8"))

        self.assertEqual(eas["cli"]["appVersionSource"], "local")
        self.assertEqual(eas["build"]["internal"]["distribution"], "internal")
        self.assertEqual(eas["build"]["internal"]["android"]["buildType"], "apk")


if __name__ == "__main__":
    unittest.main()
