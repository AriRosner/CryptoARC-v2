import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const app = readFileSync(join(root, "src", "App.tsx"), "utf8");
const api = readFileSync(join(root, "src", "api.ts"), "utf8");
const pages = ["AnalysisPage.tsx", "ReviewPage.tsx", "DataPage.tsx"].map((name) => readFileSync(join(root, "src", "pages", name), "utf8"));

const failures = [];
if (!app.includes('document.addEventListener("visibilitychange"')) failures.push("visibility backoff listener is missing");
if (!app.includes('window.addEventListener("online"') || !app.includes('window.addEventListener("offline"')) failures.push("connectivity backoff listeners are missing");
if (!app.includes('document.visibilityState !== "visible" || !navigator.onLine')) failures.push("noncritical refreshes do not fail fast while hidden or offline");
if (!api.includes('/api/monitoring/workload-pressure')) failures.push("bounded workload pressure endpoint is not consumed");
if (pages.some((source) => !source.includes('data-critical-projection='))) failures.push("a noncritical page lacks its degraded projection marker");
if (pages.some((source) => /setInterval\s*\(/.test(source))) failures.push("page-local polling loops are forbidden; App owns bounded refreshes");

if (failures.length) {
  console.error("Critical projection checks failed:");
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}
console.log("Critical projection checks passed.");
