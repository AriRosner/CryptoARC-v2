import { mobileGet, type MobileGetOptions } from "../../core/api/client";
import type { PositionDetail, PositionsPayload } from "./types";

export function fetchPositions(options?: MobileGetOptions): Promise<PositionsPayload> {
  return mobileGet<PositionsPayload>("/api/mobile/positions", options);
}

export function fetchPositionDetail(
  positionId: string,
  options?: MobileGetOptions,
): Promise<PositionDetail> {
  return mobileGet<PositionDetail>(
    `/api/mobile/positions/${encodeURIComponent(positionId)}`,
    options,
  );
}
