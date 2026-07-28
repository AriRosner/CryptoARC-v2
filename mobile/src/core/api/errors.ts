export type MobileErrorCategory =
  | "connection"
  | "authentication"
  | "authorization"
  | "validation"
  | "stale_state"
  | "conflict"
  | "rate_limit"
  | "server"
  | "compatibility"
  | "ambiguous_outcome";

export class MobileApiError extends Error {
  constructor(
    message: string,
    readonly category: MobileErrorCategory,
    readonly status: number | null,
    readonly retryable: boolean,
    readonly actionId = "",
  ) {
    super(message);
    this.name = "MobileApiError";
    Object.setPrototypeOf(this, MobileApiError.prototype);
  }
}

interface MobileErrorBody {
  action_id?: unknown;
  detail?: unknown;
  message?: unknown;
}

function errorMessage(body: MobileErrorBody, status: number, statusText: string): string {
  if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  if (typeof body.message === "string" && body.message.trim()) return body.message;
  return statusText.trim() || `Mobile request failed (${status})`;
}

export function mobileHttpError(status: number, statusText: string, body: MobileErrorBody = {}): MobileApiError {
  const actionId = typeof body.action_id === "string" ? body.action_id : "";
  const message = errorMessage(body, status, statusText);

  if (status === 401) return new MobileApiError(message, "authentication", status, false, actionId);
  if (status === 403) return new MobileApiError(message, "authorization", status, false, actionId);
  if (status === 409) return new MobileApiError(message, "conflict", status, false, actionId);
  if (status === 410 || status === 412) return new MobileApiError(message, "stale_state", status, false, actionId);
  if (status === 400 || status === 404 || status === 422) {
    return new MobileApiError(message, "validation", status, false, actionId);
  }
  if (status === 426) return new MobileApiError(message, "compatibility", status, false, actionId);
  if (status === 429) return new MobileApiError(message, "rate_limit", status, true, actionId);
  if (status >= 500) return new MobileApiError(message, "server", status, true, actionId);
  return new MobileApiError(message, "server", status, false, actionId);
}
