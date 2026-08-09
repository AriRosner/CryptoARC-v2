from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DependencyContractTests(unittest.TestCase):
    def test_cryptography_pin_excludes_pkcs7_oracle_advisory(self) -> None:
        requirements = (ROOT / "backend" / "requirements.txt").read_text(
            encoding="utf-8"
        )
        match = re.search(r"^cryptography==(\d+)\.(\d+)\.(\d+)$", requirements, re.M)

        self.assertIsNotNone(match)
        version = tuple(int(part) for part in match.groups())
        self.assertGreaterEqual(version, (50, 0, 0))


if __name__ == "__main__":
    unittest.main()
