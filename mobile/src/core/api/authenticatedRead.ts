import type { SessionContextValue } from "../session/SessionProvider";
import { MobileApiError } from "./errors";

type RevocableSession = Pick<SessionContextValue, "revokeSession">;

export async function authenticatedRead<T>(
  session: RevocableSession | null,
  operation: () => Promise<T>,
): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (session && error instanceof MobileApiError && error.status === 401) {
      await session.revokeSession();
    }
    throw error;
  }
}

export function mobileReadErrorMessage(
  error: unknown,
  resource: "Portfolio" | "positions",
): string {
  if (error instanceof MobileApiError && error.status === 401) {
    return `Pair this device again to view ${resource}.`;
  }
  if (error instanceof MobileApiError && error.status === 403) {
    return `This device does not have ${resource} access.`;
  }
  return resource === "Portfolio"
    ? "Portfolio data is unavailable. Pull to retry over the private tunnel."
    : "The private tunnel or mobile API is unavailable.";
}
