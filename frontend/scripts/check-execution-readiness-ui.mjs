import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const typesSource = readFileSync(join(here, "..", "src", "types.ts"), "utf8");
const analysisSource = readFileSync(join(here, "..", "src", "pages", "AnalysisPage.tsx"), "utf8");

const typeFields = [
  "quote_evidence_window_hours",
  "current_latest_quote_age_seconds",
  "current_quote_attempts",
  "current_stale_quote_rate",
  "current_unhealthy_quote_rate",
  "current_blocked_quotes",
  "current_failed_quotes",
  "current_quote_issues",
  "current_failure_stages",
  "current_latency_summary",
  "audit_history_limit",
  "audit_history_truncated",
  "audit_history_complete",
];

const missingTypeFields = typeFields.filter((field) => !typesSource.includes(field));
if (missingTypeFields.length) {
  throw new Error(`Execution readiness types are missing: ${missingTypeFields.join(", ")}`);
}

if (!/current_quote_health_sample_kind:\s*"current_quote_audits";/.test(typesSource)) {
  throw new Error("Execution readiness type must use the backend's current_quote_audits sample-kind literal");
}

const uiChecks = [
  {
    name: "current quote attempts drive the primary quote card",
    pattern: /execution\.metrics\.current_quote_attempts/,
  },
  {
    name: "current stale rate drives the primary stale card",
    pattern: /execution\.metrics\.current_stale_quote_rate/,
  },
  {
    name: "current unhealthy rate drives the primary unhealthy card",
    pattern: /execution\.metrics\.current_unhealthy_quote_rate/,
  },
  {
    name: "the current evidence window is explicit",
    pattern: /quote_evidence_window_hours/,
  },
  {
    name: "loaded history is explicitly labelled",
    pattern: />Loaded history</,
  },
  {
    name: "current quote diagnostics are rendered",
    pattern: /execution\.current_quote_issues/,
  },
  {
    name: "current failure diagnostics are rendered",
    pattern: /execution\.current_failure_stages/,
  },
];

const failedUiChecks = uiChecks.filter((check) => !check.pattern.test(analysisSource));
if (failedUiChecks.length) {
  throw new Error(`Execution readiness UI checks failed: ${failedUiChecks.map((check) => check.name).join("; ")}`);
}

console.log("Execution readiness UI checks passed.");
