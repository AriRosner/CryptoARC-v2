import { mobileGet, type MobileGetOptions } from "../../core/api/client";
import type { MobileDiagnosticsPayload } from "./types";

export function fetchDiagnostics(
  options?: MobileGetOptions,
): Promise<MobileDiagnosticsPayload> {
  return mobileGet<MobileDiagnosticsPayload>(
    "/api/mobile/diagnostics",
    options,
  );
}

export function exportDiagnostics(
  options?: MobileGetOptions,
): Promise<Record<string, unknown>> {
  return mobileGet<Record<string, unknown>>(
    "/api/mobile/diagnostics/export",
    options,
  );
}
