import { useQuery } from "@tanstack/react-query";

import { authenticatedRead } from "../../core/api/authenticatedRead";
import { useOptionalSession } from "../../core/session/SessionProvider";
import {
  fetchDestinations,
  fetchWallet,
  fetchWalletTransactions,
} from "./api";

function useWalletRead<T>(
  key: string,
  read: Parameters<typeof authenticatedRead<T>>[1],
) {
  const session = useOptionalSession();
  const generation = session?.generation ?? "test";
  return useQuery({
    queryKey: ["mobile", "wallet", key, generation],
    queryFn: () => authenticatedRead(session, read),
    enabled: session === null || (!session.loading && Boolean(session.token)),
  });
}

export function useWalletQuery() {
  const session = useOptionalSession();
  const options = session
    ? { apiBaseUrl: session.apiBaseUrl, token: session.token }
    : undefined;
  return useWalletRead("summary", () => fetchWallet(options));
}

export function useWalletTransactionsQuery() {
  const session = useOptionalSession();
  const options = session
    ? { apiBaseUrl: session.apiBaseUrl, token: session.token }
    : undefined;
  return useWalletRead("transactions", () =>
    fetchWalletTransactions(options),
  );
}

export function useDestinationsQuery() {
  const session = useOptionalSession();
  const options = session
    ? { apiBaseUrl: session.apiBaseUrl, token: session.token }
    : undefined;
  return useWalletRead("destinations", () => fetchDestinations(options));
}
