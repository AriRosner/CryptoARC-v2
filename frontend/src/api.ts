import type { BacktestResult, BotSnapshot, DataSummary, SecurityStatus, SourceEvent, SourceHealth, TradeRecord } from "./types";

const API_BASE = "http://127.0.0.1:8000";
let authToken = window.localStorage.getItem("cryptoarc_token") || "";

function headers(extra?: HeadersInit): HeadersInit {
  return authToken ? { ...extra, Authorization: `Bearer ${authToken}` } : { ...extra };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers: headers(init.headers) });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function authStatus(): Promise<{ enabled: boolean; totp_enabled: boolean }> {
  return request("/api/auth/status");
}

export async function login(password: string, code: string): Promise<void> {
  const result = await request<{ token: string }>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password, code })
  });
  authToken = result.token;
  window.localStorage.setItem("cryptoarc_token", authToken);
}

export async function fetchSnapshot(): Promise<BotSnapshot> {
  return request("/api/snapshot");
}

export async function startBot(): Promise<BotSnapshot> {
  return request("/api/start", { method: "POST" });
}

export async function stopBot(): Promise<BotSnapshot> {
  return request("/api/stop", { method: "POST" });
}

export async function patchSettings(patch: Record<string, number | boolean | string>): Promise<BotSnapshot> {
  return request("/api/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch)
  });
}

export async function runReplayBacktest(options?: { limit?: number; profile?: string }): Promise<BacktestResult> {
  return request("/api/backtest/replay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options ?? {})
  });
}

export async function runRawReplayBacktest(options?: { limit?: number; profile?: string }): Promise<BacktestResult> {
  return request("/api/backtest/raw-replay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options ?? {})
  });
}

export async function runStrategyComparison(): Promise<BacktestResult> {
  return request("/api/backtest/compare", { method: "POST" });
}

export async function fetchBacktests(): Promise<BacktestResult[]> {
  return request("/api/backtests");
}

export async function fetchSourceEvents(): Promise<SourceEvent[]> {
  return request("/api/source-events");
}

export async function fetchTrades(): Promise<TradeRecord[]> {
  return request("/api/trades");
}

export async function fetchSourceHealth(): Promise<SourceHealth> {
  return request("/api/source-health");
}

export async function fetchSecurityStatus(): Promise<SecurityStatus> {
  return request("/api/security/status");
}

export async function fetchDataSummary(): Promise<DataSummary> {
  return request("/api/data/summary");
}

export async function clearData(target: "tokens" | "events" | "source_events" | "backtests" | "trades" | "all"): Promise<DataSummary> {
  return request(`/api/data/clear/${target}`, { method: "POST" });
}

export function exportUrl(target: "tokens" | "source_events" | "backtests" | "trades" | "all"): string {
  return `${API_BASE}/api/export/${target}${authToken ? `?token=${encodeURIComponent(authToken)}` : ""}`;
}

export function openSnapshotSocket(onSnapshot: (snapshot: BotSnapshot) => void): WebSocket {
  const socket = new WebSocket(`ws://127.0.0.1:8000/ws${authToken ? `?token=${encodeURIComponent(authToken)}` : ""}`);
  socket.addEventListener("message", (event) => {
    onSnapshot(JSON.parse(event.data));
  });
  return socket;
}
