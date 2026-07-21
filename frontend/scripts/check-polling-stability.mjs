import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(join(here, "..", "src", "App.tsx"), "utf8");

function extractCallExpressions(source, callee) {
  const calls = [];
  let searchFrom = 0;
  while ((searchFrom = source.indexOf(callee, searchFrom)) !== -1) {
    const openParen = source.indexOf("(", searchFrom + callee.length);
    if (openParen === -1) break;

    let depth = 0;
    let quote = null;
    let escaped = false;
    let closed = false;
    for (let index = openParen; index < source.length; index += 1) {
      const char = source[index];
      if (quote) {
        if (escaped) {
          escaped = false;
        } else if (char === "\\") {
          escaped = true;
        } else if (char === quote) {
          quote = null;
        }
        continue;
      }
      if (char === '"' || char === "'" || char === "`") {
        quote = char;
      } else if (char === "(") {
        depth += 1;
      } else if (char === ")" && --depth === 0) {
        calls.push(source.slice(searchFrom, index + 1));
        searchFrom = index + 1;
        closed = true;
        break;
      }
    }
    if (!closed) break;
  }
  return calls;
}

if (extractCallExpressions("React.useEffect(() => {", "React.useEffect").length !== 0) {
  throw new Error("incomplete call expressions must be ignored");
}

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

const presetRefreshCalls = appSource.match(/\brefreshStrategyPresetData\s*\(/g) ?? [];
const presetSettingsEffects = extractCallExpressions(appSource, "React.useEffect").filter(
  (effect) =>
    /if\s*\(\s*!settingsOpen\s*\)\s*return\s*;/.test(effect) &&
    /\brefreshStrategyPresetData\s*\(/.test(effect),
);

if (presetRefreshCalls.length !== 1 || presetSettingsEffects.length !== 1) {
  console.error("Polling stability checks failed:");
  console.error("- strategy presets must refresh exactly once, from the effect gated by settingsOpen");
  process.exit(1);
}

console.log("Polling stability checks passed.");
