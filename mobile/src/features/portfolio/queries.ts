import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { authenticatedRead } from "../../core/api/authenticatedRead";
import { useOptionalSession } from "../../core/session/SessionProvider";
import { fetchPortfolio } from "./api";
import type { PortfolioTimeframe } from "./types";

export function usePortfolioQuery(timeframe: PortfolioTimeframe) {
  const session = useOptionalSession();
  const enabled = session === null || Boolean(session.token);
  return useQuery({
    queryKey: ["mobile", "portfolio", timeframe, session?.generation ?? "test"],
    queryFn: () =>
      authenticatedRead(session, () =>
        session
          ? fetchPortfolio(timeframe, {
              apiBaseUrl: session.apiBaseUrl,
              token: session.token,
            })
          : fetchPortfolio(timeframe),
      ),
    enabled,
    placeholderData: keepPreviousData,
  });
}
