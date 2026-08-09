from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendBuildConfigTests(unittest.TestCase):
    def test_vite_uses_rolldown_code_splitting_groups(self) -> None:
        config = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")

        self.assertNotIn("manualChunks", config)
        self.assertIn("rolldownOptions", config)
        self.assertIn("codeSplitting", config)
        for chunk in (
            "chart-vendor",
            "solana-vendor",
            "motion-vendor",
            "icon-vendor",
        ):
            self.assertIn(chunk, config)


if __name__ == "__main__":
    unittest.main()
