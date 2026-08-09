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
): Promise<MobileDiagnosticsPayload & { exported_at: string }> {
  return mobileGet<MobileDiagnosticsPayload & { exported_at: string }>(
    "/api/mobile/diagnostics/export",
    options,
  );
}
