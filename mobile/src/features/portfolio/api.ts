import { mobileGet, type MobileGetOptions } from "../../core/api/client";
import type { PortfolioPayload, PortfolioTimeframe } from "./types";

export function fetchPortfolio(
  timeframe: PortfolioTimeframe,
  options?: MobileGetOptions,
): Promise<PortfolioPayload> {
  return mobileGet<PortfolioPayload>(
    `/api/mobile/portfolio?timeframe=${encodeURIComponent(timeframe)}`,
    options,
  );
}
