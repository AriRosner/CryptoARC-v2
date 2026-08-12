from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GitHubWorkflowContractTests(unittest.TestCase):
    def test_workflows_use_current_checkout_runtime(self) -> None:
        workflows = ROOT / ".github" / "workflows"
        workflow_text = "\n".join(
            path.read_text(encoding="utf-8") for path in workflows.glob("*.yml")
        )

        self.assertNotIn("actions/checkout@v4", workflow_text)
        self.assertEqual(workflow_text.count("actions/checkout@v7"), 8)

    def test_code_line_badge_updates_main_through_a_pull_request(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "update-code-lines.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("pull-requests: write", workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn("gh pr create", workflow)
        self.assertIn("actions/runs/$runId/approve", workflow)
        self.assertIn("gh run watch $runId --exit-status", workflow)
        self.assertIn(
            "gh pr merge $prNumber --auto --squash --delete-branch",
            workflow,
        )
        self.assertIn("Delete stale badge branch", workflow)
        self.assertIn("--state open --head $branch", workflow)
        self.assertIn("automation/code-line-badge-${{ github.run_id }}", workflow)
        self.assertIn("group: update-code-line-badge", workflow)
        self.assertNotIn("group: update-code-line-badge-${{ github.ref }}", workflow)
        self.assertNotIn("git push origin HEAD:${{ github.ref_name }}", workflow)
        self.assertNotIn("[skip ci]", workflow)

    def test_mobile_audit_exception_is_checked_weekly(self) -> None:
        workflow_path = ROOT / ".github" / "workflows" / "mobile-audit-exception.yml"
        self.assertTrue(workflow_path.exists())
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn("schedule:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("scripts/audit-mobile.ps1 -Strict", workflow)
        self.assertIn("scripts/check-mobile-audit-upstream.ps1", workflow)

    def test_ci_runs_the_full_mobile_gate(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("  mobile:\n", workflow)
        self.assertIn("cache-dependency-path: mobile/package-lock.json", workflow)
        self.assertIn("npm ci --legacy-peer-deps", workflow)
        self.assertIn("./scripts/verify-mobile.ps1", workflow)


if __name__ == "__main__":
    unittest.main()
