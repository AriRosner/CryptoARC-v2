from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from app.core.state import BotState  # noqa: E402
from check_settings_contract import extract_braced_block, extract_top_level_fields  # noqa: E402


class WatchdogContractTests(unittest.TestCase):
    def test_frontend_required_fields_match_runtime_watchdog_payload(self) -> None:
        frontend = (ROOT / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")
        marker = re.search(r"\bexport\s+interface\s+WatchdogStatus\b", frontend)
        self.assertIsNotNone(marker)
        assert marker is not None
        frontend_fields = extract_top_level_fields(extract_braced_block(frontend, marker.end()))

        with TemporaryDirectory() as directory:
            backend_fields = set(BotState(database_path=str(Path(directory) / "watchdog.db")).watchdog_status())

        self.assertEqual(frontend_fields - backend_fields, set())


if __name__ == "__main__":
    unittest.main()
