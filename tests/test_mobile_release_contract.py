import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_APP_VERSION = "2.0.0"
EXPECTED_ANDROID_VERSION_CODE = 4
EXPECTED_ANDROID_PACKAGE = "com.cryptoarc.cockpit"
EXPECTED_BUILD_INFO = {
    "version": EXPECTED_APP_VERSION,
    "androidVersionCode": EXPECTED_ANDROID_VERSION_CODE,
    "label": "Operator Command Center",
    "date": "2026-07-26",
}
BUILD_INFO_EXPORT = re.compile(
    r"\A\s*export\s+const\s+buildInfo\s*=\s*\{(?P<body>.*?)\}\s+as\s+const;\s*\Z",
    re.DOTALL,
)
STRING_FIELD = re.compile(r'^\s*(version|label|date):\s*"([^"]*)",\s*$')
INTEGER_FIELD = re.compile(r"^\s*(androidVersionCode):\s*(\d+),\s*$")


def extract_build_info(source: str) -> dict[str, str | int]:
    exported = BUILD_INFO_EXPORT.fullmatch(source)
    if exported is None:
        raise ValueError("buildInfo.ts must contain only the exported buildInfo object")

    fields: dict[str, str | int] = {}
    for line in exported.group("body").splitlines():
        if not line.strip():
            continue
        string_field = STRING_FIELD.fullmatch(line)
        integer_field = INTEGER_FIELD.fullmatch(line)
        field = string_field or integer_field
        if field is None:
            raise ValueError(f"Unsupported buildInfo field syntax: {line.strip()}")
        name = field.group(1)
        if name in fields:
            raise ValueError(f"Duplicate buildInfo field: {name}")
        value = field.group(2)
        fields[name] = int(value) if integer_field else value

    if set(fields) != set(EXPECTED_BUILD_INFO):
        raise ValueError("buildInfo must contain exactly the release contract fields")
    return fields


def release_app(version_code: int = EXPECTED_ANDROID_VERSION_CODE) -> dict[str, object]:
    return {
        "expo": {
            "version": EXPECTED_APP_VERSION,
            "android": {
                "package": EXPECTED_ANDROID_PACKAGE,
                "versionCode": version_code,
            },
        }
    }


class MobileReleaseContractTests(unittest.TestCase):
    def assert_release_metadata(self, app: dict[str, object], build_info: str) -> None:
        expo = app["expo"]
        self.assertIsInstance(expo, dict)
        android = expo["android"]
        self.assertIsInstance(android, dict)
        parsed_build_info = extract_build_info(build_info)

        self.assertEqual(expo["version"], EXPECTED_APP_VERSION)
        self.assertEqual(android["versionCode"], EXPECTED_ANDROID_VERSION_CODE)
        self.assertEqual(android["package"], EXPECTED_ANDROID_PACKAGE)
        self.assertEqual(parsed_build_info, EXPECTED_BUILD_INFO)
        self.assertEqual(parsed_build_info["version"], expo["version"])
        self.assertEqual(
            parsed_build_info["androidVersionCode"], android["versionCode"]
        )

    def test_command_center_release_metadata_is_exact_and_cross_checked(self) -> None:
        app = json.loads((ROOT / "mobile" / "app.json").read_text(encoding="utf-8"))
        build_info = (ROOT / "mobile" / "src" / "buildInfo.ts").read_text(
            encoding="utf-8"
        )

        self.assert_release_metadata(app, build_info)

    def test_version_code_three_cannot_satisfy_release_contract(self) -> None:
        app = release_app(version_code=3)
        build_info = """export const buildInfo = {
  version: "2.0.0",
  androidVersionCode: 3,
  label: "Operator Command Center",
  date: "2026-07-26",
} as const;
"""

        with self.assertRaises(AssertionError):
            self.assert_release_metadata(app, build_info)

    def test_comments_cannot_fake_build_info(self) -> None:
        app = release_app()
        build_info = """export const buildInfo = {
  version: "9.9.9",
  androidVersionCode: 99,
  label: "Not the release label",
  date: "2099-01-01",
  // androidVersionCode: 3
  // label: "Operator Command Center"
  // date: "2026-07-26"
} as const;
"""

        with self.assertRaises((AssertionError, ValueError)):
            self.assert_release_metadata(app, build_info)

    def test_unrelated_substrings_cannot_fake_build_info(self) -> None:
        app = release_app()
        build_info = """const unrelated = 'version 2.0.0; androidVersionCode: 3';
export const buildInfo = {
  version: "9.9.9",
  androidVersionCode: 99,
  label: "Not the release label",
  date: "2099-01-01",
} as const;
"""

        with self.assertRaises((AssertionError, ValueError)):
            self.assert_release_metadata(app, build_info)

    def test_internal_profile_produces_an_installable_apk(self) -> None:
        eas = json.loads((ROOT / "mobile" / "eas.json").read_text(encoding="utf-8"))

        self.assertEqual(eas["cli"]["appVersionSource"], "local")
        self.assertEqual(eas["build"]["internal"]["distribution"], "internal")
        self.assertEqual(eas["build"]["internal"]["android"]["buildType"], "apk")


if __name__ == "__main__":
    unittest.main()
