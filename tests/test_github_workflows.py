from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GitHubWorkflowContractTests(unittest.TestCase):
    def test_code_line_badge_updates_main_through_a_pull_request(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "update-code-lines.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("pull-requests: write", workflow)
        self.assertIn("gh pr create", workflow)
        self.assertIn("gh pr merge", workflow)
        self.assertIn("automation/code-line-badge-${{ github.run_id }}", workflow)
        self.assertNotIn("git push origin HEAD:${{ github.ref_name }}", workflow)


if __name__ == "__main__":
    unittest.main()
