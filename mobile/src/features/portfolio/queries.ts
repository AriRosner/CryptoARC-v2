import { useQuery } from "@tanstack/react-query";

import { authenticatedRead } from "../../core/api/authenticatedRead";
import { useOptionalSession } from "../../core/session/SessionProvider";
import { fetchPortfolio } from "./api";
import type { PortfolioTimeframe } from "./types";

export function usePortfolioQuery(timeframe: PortfolioTimeframe) {
  const session = useOptionalSession();
  const sessionGeneration = session?.generation ?? "test";
  const enabled =
    session === null || (!session.loading && Boolean(session.token));
  return useQuery({
    queryKey: ["mobile", "portfolio", timeframe, sessionGeneration],
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
    placeholderData: (previousData, previousQuery) =>
      previousQuery?.queryKey.at(-1) === sessionGeneration
        ? previousData
        : undefined,
  });
}
