export function controlsRequireUnlock(token: string | null, locked: boolean): boolean {
  return Boolean(token && locked);
}

export function sanitizeReason(value: string): string {
  return value.trim().replace(/\s+/g, " ").slice(0, 500);
}

export function parsePairingPayload(value: string): { pairingId: string; code: string; apiBaseUrl: string } {
  const parsed = JSON.parse(value);
  const pairingId = String(parsed.pairing_id || "");
  const code = String(parsed.code || "");
  const apiBaseUrl = String(parsed.api_base_url || "");
  if (!pairingId || !code) {
    throw new Error("Pairing QR is missing its code");
  }
  return { pairingId, code, apiBaseUrl };
}
