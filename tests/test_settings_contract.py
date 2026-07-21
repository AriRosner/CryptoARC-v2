import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from check_settings_contract import (  # noqa: E402
    compare_field_sets,
    extract_braced_block,
    extract_fallback_settings_fields,
    load_contract_fields,
)


class SettingsContractTests(unittest.TestCase):
    def test_compare_field_sets_reports_sorted_missing_and_extra_fields(self) -> None:
        messages = compare_field_sets(
            {"alpha", "beta", "gamma"},
            {"alpha", "delta"},
            "frontend interface",
        )

        self.assertEqual(
            messages,
            [
                "frontend interface: missing fields: beta, gamma",
                "frontend interface: extra fields: delta",
            ],
        )

    def test_extract_braced_block_rejects_unterminated_block(self) -> None:
        with self.assertRaisesRegex(ValueError, "unterminated brace-delimited block"):
            extract_braced_block("const settings = { enabled: true", 0)

    def test_fallback_settings_uses_only_direct_top_level_property(self) -> None:
        source = '''
const fallbackSnapshot: BotSnapshot = {
  metadata: { settings: { nested: true } },
  // settings: { lineComment: true }
  /* settings: { blockComment: true } */
  note: "settings: { quoted: true }",
  template: `settings: { templated: true }`,
  settings: { direct: true }
};
'''

        self.assertEqual({"direct"}, extract_fallback_settings_fields(source))

    def test_fallback_settings_requires_direct_top_level_property(self) -> None:
        source = '''
const fallbackSnapshot: BotSnapshot = {
  metadata: { settings: { nested: true } },
  // settings: { lineComment: true }
  note: "settings: { quoted: true }"
};
'''

        with self.assertRaisesRegex(ValueError, "fallbackSnapshot settings object not found"):
            extract_fallback_settings_fields(source)

    def test_current_repository_settings_contract_is_in_parity(self) -> None:
        backend_fields, frontend_fields, fallback_fields = load_contract_fields(ROOT)

        self.assertEqual([], compare_field_sets(backend_fields, frontend_fields, "frontend interface"))
        self.assertEqual([], compare_field_sets(backend_fields, fallback_fields, "fallback snapshot"))


if __name__ == "__main__":
    unittest.main()
