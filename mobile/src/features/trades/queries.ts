import { useQuery } from "@tanstack/react-query";

import { authenticatedRead } from "../../core/api/authenticatedRead";
import { useOptionalSession } from "../../core/session/SessionProvider";
import { fetchAction, fetchTrade, fetchTrades } from "./api";

export function useTradesQuery() {
  const session = useOptionalSession();
  const generation = session?.generation ?? "test";
  return useQuery({
    queryKey: ["mobile", "trades", generation],
    queryFn: () =>
      authenticatedRead(session, () =>
        session
          ? fetchTrades({
              apiBaseUrl: session.apiBaseUrl,
              token: session.token,
            })
          : fetchTrades(),
      ),
    enabled: session === null || (!session.loading && Boolean(session.token)),
  });
}

export function useTradeQuery(intentId: string) {
  const session = useOptionalSession();
  const generation = session?.generation ?? "test";
  return useQuery({
    queryKey: ["mobile", "trade", intentId, generation],
    queryFn: () =>
      authenticatedRead(session, () =>
        session
          ? fetchTrade(intentId, {
              apiBaseUrl: session.apiBaseUrl,
              token: session.token,
            })
          : fetchTrade(intentId),
      ),
    enabled:
      Boolean(intentId) &&
      (session === null || (!session.loading && Boolean(session.token))),
  });
}

export function useActionQuery(
  actionId: string,
  reconcileAfterMs: number,
  enabled: boolean,
) {
  const session = useOptionalSession();
  const generation = session?.generation ?? "test";
  return useQuery({
    queryKey: ["mobile", "action", actionId, generation],
    queryFn: () =>
      authenticatedRead(session, () =>
        session
          ? fetchAction(actionId, {
              apiBaseUrl: session.apiBaseUrl,
              token: session.token,
            })
          : fetchAction(actionId),
      ),
    enabled:
      enabled &&
      Boolean(actionId) &&
      (session === null || (!session.loading && Boolean(session.token))),
    refetchInterval: (query) =>
      ["pending", "verifying"].includes(String(query.state.data?.status ?? ""))
        ? Math.max(250, Math.min(30000, reconcileAfterMs))
        : false,
  });
}
