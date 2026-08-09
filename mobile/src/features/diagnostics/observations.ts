import type { MobileDiagnosticsPayload } from "./types";

interface ClientDiagnosticObservations {
  apiBaseUrl: string;
  apiStartedAt: string;
  apiReceivedAt: string;
  now: string;
  online: boolean;
  realtime: {
    status: string;
    lastServerTime: string;
  };
  verifiedSnapshot: {
    verifiedAt: string;
    serverTime: string;
  } | null;
}

function milliseconds(value: string): number | null {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function privateTunnelUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname.endsWith(".ts.net");
  } catch {
    return false;
  }
}

export function applyClientDiagnosticObservations(
  payload: MobileDiagnosticsPayload,
  observations: ClientDiagnosticObservations,
): MobileDiagnosticsPayload {
  const receivedAt = milliseconds(observations.apiReceivedAt);
  const startedAt = milliseconds(observations.apiStartedAt);
  const now = milliseconds(observations.now);
  const serverAt = milliseconds(payload.generated_at);
  const observedAt = receivedAt === null ? null : observations.apiReceivedAt;
  const updates = new Map<
    string,
    Pick<MobileDiagnosticsPayload["checks"][number], "status" | "detail" | "observed_at">
  >();

  updates.set("api", {
    status: observedAt ? "healthy" : "unavailable",
    detail: observedAt
      ? "Authenticated API response observed on-device."
      : "No bounded API observation is available.",
    observed_at: observedAt,
  });
  updates.set("tunnel", {
    status: !observations.online
      ? "warning"
      : privateTunnelUrl(observations.apiBaseUrl)
        ? "healthy"
        : "unavailable",
    detail: !observations.online
      ? "Device connectivity is offline."
      : privateTunnelUrl(observations.apiBaseUrl)
        ? "Authenticated API response used the configured tailnet host."
        : "Configured API URL does not prove a private-tunnel path.",
    observed_at: observedAt,
  });
  updates.set("websocket", {
    status:
      observations.realtime.status === "connected"
        ? "healthy"
        : observations.realtime.status === "offline" ||
            observations.realtime.status === "stale"
          ? "warning"
          : "unavailable",
    detail:
      observations.realtime.status === "connected"
        ? "Active WebSocket connection observed on-device."
        : `On-device WebSocket state: ${observations.realtime.status}.`,
    observed_at:
      milliseconds(observations.realtime.lastServerTime) === null
        ? observedAt
        : observations.realtime.lastServerTime,
  });

  const roundTripMs =
    startedAt === null || receivedAt === null ? null : receivedAt - startedAt;
  if (
    roundTripMs === null ||
    roundTripMs < 0 ||
    roundTripMs > 10_000 ||
    serverAt === null
  ) {
    updates.set("clock_drift", {
      status: "unavailable",
      detail: "Clock drift requires an API round trip of 10 seconds or less.",
      observed_at: null,
    });
  } else {
    const midpoint = startedAt! + roundTripMs / 2;
    const driftMs = Math.round(serverAt - midpoint);
    updates.set("clock_drift", {
      status: Math.abs(driftMs) <= 5_000 ? "healthy" : "warning",
      detail: `Estimated device clock drift is ${Math.abs(driftMs)} ms.`,
      observed_at: observedAt,
    });
  }

  let freshness: MobileDiagnosticsPayload["freshness"] = {
    status: "unavailable",
    age_seconds: null,
    stale_after_seconds: payload.freshness.stale_after_seconds,
  };
  if (observations.verifiedSnapshot && now !== null) {
    const verifiedAt = milliseconds(observations.verifiedSnapshot.verifiedAt);
    if (verifiedAt !== null) {
      const ageSeconds = Math.max(0, Math.floor((now - verifiedAt) / 1000));
      const fresh = ageSeconds <= payload.freshness.stale_after_seconds;
      freshness = {
        status: fresh ? "fresh" : "stale",
        age_seconds: ageSeconds,
        stale_after_seconds: payload.freshness.stale_after_seconds,
      };
      updates.set("snapshot_age", {
        status: fresh ? "healthy" : "warning",
        detail: `Latest verified mobile snapshot is ${ageSeconds} seconds old.`,
        observed_at: observations.verifiedSnapshot.verifiedAt,
      });
    }
  }
  if (!updates.has("snapshot_age")) {
    updates.set("snapshot_age", {
      status: "unavailable",
      detail: "No verified mobile snapshot observation is available.",
      observed_at: null,
    });
  }

  return {
    ...payload,
    freshness,
    checks: payload.checks.map((check) => ({
      ...check,
      ...(updates.get(check.id) ?? {}),
    })),
  };
}
