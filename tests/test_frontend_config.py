from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendConfigContractTests(unittest.TestCase):
    def test_vite_typescript_uses_bundler_module_resolution(self) -> None:
        config = json.loads(
            (ROOT / "frontend" / "tsconfig.json").read_text(encoding="utf-8")
        )

        self.assertEqual(config["compilerOptions"]["module"], "ESNext")
        self.assertEqual(config["compilerOptions"]["moduleResolution"], "Bundler")


if __name__ == "__main__":
    unittest.main()
