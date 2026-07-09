import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(join(here, "..", "src", "App.tsx"), "utf8");

const checks = [
  {
    name: "refreshSolUsdPrice is a stable callback",
    pattern: /const\s+refreshSolUsdPrice\s*=\s*React\.useCallback\(/,
  },
  {
    name: "refreshPnlData is a stable callback",
    pattern: /const\s+refreshPnlData\s*=\s*React\.useCallback\(/,
  },
  {
    name: "SOL/USD refresh has an in-flight guard",
    pattern: /solUsdRefreshInFlight\.current/,
  },
  {
    name: "latency refresh has an in-flight guard",
    pattern: /latencyRefreshInFlight\.current/,
  },
  {
    name: "initial workspace refresh is guarded by a last-run key",
    pattern: /workspaceRefreshKeyRef\.current/,
  },
  {
    name: "latency failures preserve the last known payload",
    pattern: /latency_error/,
  },
];

const failures = checks.filter((check) => !check.pattern.test(appSource));

if (failures.length) {
  console.error("Polling stability checks failed:");
  for (const failure of failures) {
    console.error(`- ${failure.name}`);
  }
  process.exit(1);
}

if (/setLatencyStatus\(null\)/.test(appSource)) {
  console.error("Polling stability checks failed:");
  console.error("- latency failures must not clear the last known payload");
  process.exit(1);
}

console.log("Polling stability checks passed.");
