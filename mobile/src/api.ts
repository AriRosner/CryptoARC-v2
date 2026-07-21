import type { MobileCockpitPayload, MobileFeedPayload, PairingClaimResponse } from "./types";

const MOBILE_COCKPIT_TIMEOUT_MS = 10000;

export interface PairingClaimInput {
  apiBaseUrl: string;
  pairingId: string;
  code: string;
  deviceName: string;
  platform?: string;
}

export function normalizeApiBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

async function mobileRequest<T>(apiBaseUrl: string, path: string, token?: string, init: RequestInit = {}): Promise<T> {
  const base = normalizeApiBaseUrl(apiBaseUrl);
  if (!base) {
    throw new Error("Private tunnel API URL is required");
  }
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${base}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      // Response body is optional for health and auth failures.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function probeMobileHealth(apiBaseUrl: string): Promise<Record<string, unknown>> {
  return mobileRequest<Record<string, unknown>>(apiBaseUrl, "/api/mobile/health");
}

export async function claimMobilePairing(input: PairingClaimInput): Promise<PairingClaimResponse> {
  return mobileRequest<PairingClaimResponse>(input.apiBaseUrl, "/api/mobile/pairing/claim", undefined, {
    method: "POST",
    body: JSON.stringify({
      pairing_id: input.pairingId,
      code: input.code,
      device_name: input.deviceName,
      platform: input.platform ?? "android",
    }),
  });
}

export async function fetchMobileCockpit(apiBaseUrl: string, token: string): Promise<MobileCockpitPayload> {
  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error("Cockpit refresh timed out"));
      controller.abort();
    }, MOBILE_COCKPIT_TIMEOUT_MS);
  });
  try {
    return await Promise.race([
      mobileRequest<MobileCockpitPayload>(apiBaseUrl, "/api/mobile/cockpit", token, { signal: controller.signal }),
      timeout,
    ]);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}

export async function fetchMobileFeed(apiBaseUrl: string, token: string, level = "", subsystem = ""): Promise<MobileFeedPayload> {
  const params = new URLSearchParams();
  if (level) params.set("level", level);
  if (subsystem) params.set("subsystem", subsystem);
  params.set("limit", "200");
  return mobileRequest<MobileFeedPayload>(apiBaseUrl, `/api/mobile/feed?${params.toString()}`, token);
}

export async function startMobileBot(apiBaseUrl: string, token: string): Promise<MobileCockpitPayload> {
  return mobileRequest<MobileCockpitPayload>(apiBaseUrl, "/api/mobile/actions/start", token, { method: "POST" });
}

export async function stopMobileBot(apiBaseUrl: string, token: string): Promise<MobileCockpitPayload> {
  return mobileRequest<MobileCockpitPayload>(apiBaseUrl, "/api/mobile/actions/stop", token, { method: "POST" });
}

export async function setMobileKillSwitch(
  apiBaseUrl: string,
  token: string,
  enabled: boolean,
  reason: string,
): Promise<MobileCockpitPayload> {
  return mobileRequest<MobileCockpitPayload>(apiBaseUrl, "/api/mobile/actions/kill-switch", token, {
    method: "POST",
    body: JSON.stringify({ enabled, reason }),
  });
}

export function mobileWebSocketUrl(apiBaseUrl: string, token: string): string {
  const base = normalizeApiBaseUrl(apiBaseUrl);
  const wsBase = base.replace(/^https:/i, "wss:").replace(/^http:/i, "ws:");
  return `${wsBase}/ws/mobile?token=${encodeURIComponent(token)}`;
}
