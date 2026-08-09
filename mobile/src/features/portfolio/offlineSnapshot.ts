import type { MobileDevice } from "../../types";
import {
  createSnapshotBinding,
  loadVerifiedSnapshot,
  saveVerifiedSnapshot,
  type VerifiedSnapshot,
} from "../../core/storage/snapshot";
import type { PortfolioPayload } from "./types";

interface SnapshotSession {
  apiBaseUrl: string;
  token: string | null;
  device: MobileDevice | null;
}

async function bindingFor(session: SnapshotSession) {
  if (!session.token || !session.device?.id) return null;
  return createSnapshotBinding({
    apiBaseUrl: session.apiBaseUrl,
    token: session.token,
    deviceId: session.device.id,
  });
}

export async function saveVerifiedPortfolioSnapshot(
  session: SnapshotSession,
  payload: PortfolioPayload,
): Promise<void> {
  const binding = await bindingFor(session);
  if (!binding) return;
  if (
    payload.artifact_type !== "cryptoarc_mobile_portfolio" ||
    payload.format_version !== 1 ||
    !Number.isFinite(Date.parse(payload.generated_at))
  ) {
    return;
  }
  await saveVerifiedSnapshot({
    schemaVersion: 1,
    ...binding,
    verifiedAt: new Date().toISOString(),
    serverTime: payload.generated_at,
    sequence: 0,
    payload: {
      kind: "portfolio",
      version: 1,
      data: {
        totalValueSol: payload.summary.tracked_value_sol,
        assets: payload.allocation.map((item) => ({
          assetIdentifier: {
            kind: "public_asset" as const,
            chain: "solana",
            value: item.key,
          },
          assetMetadata: { symbol: item.label },
          balance: 0,
          valueSol: item.value_sol,
        })),
      },
    },
  });
}

export async function loadVerifiedPortfolioSnapshot(
  session: SnapshotSession,
): Promise<VerifiedSnapshot | null> {
  const binding = await bindingFor(session);
  if (!binding) return null;
  const snapshot = await loadVerifiedSnapshot(binding);
  return snapshot?.payload.kind === "portfolio" ? snapshot : null;
}
