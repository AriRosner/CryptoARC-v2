import { MobileApiError, mobileHttpError } from "./errors";

const DEFAULT_TIMEOUT_MS = 10000;

interface MobileRequestOptions {
  apiBaseUrl?: string;
  token?: string | null;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export interface MobileGetOptions extends MobileRequestOptions {
  headers?: HeadersInit;
}

export interface MobileActionOptions<TBody> extends MobileRequestOptions {
  idempotencyKey: string;
  body: TBody;
  method?: "POST" | "PUT" | "PATCH" | "DELETE";
  headers?: HeadersInit;
}

function requestUrl(apiBaseUrl: string | undefined, path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  const base = (apiBaseUrl ?? "").trim().replace(/\/+$/, "");
  return base ? `${base}${path.startsWith("/") ? path : `/${path}`}` : path;
}

async function responseBody(response: Response): Promise<Record<string, unknown>> {
  try {
    const body: unknown = await response.json();
    return body !== null && typeof body === "object" ? (body as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

async function dispatch<T>(
  path: string,
  options: MobileRequestOptions,
  init: RequestInit,
  ambiguousOnNetworkLoss: boolean,
): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  let timedOut = false;
  const onExternalAbort = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  options.signal?.addEventListener("abort", onExternalAbort, { once: true });
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);

  try {
    const response = await fetch(requestUrl(options.apiBaseUrl, path), {
      ...init,
      headers,
      signal: controller.signal,
    });
    const body = await responseBody(response);
    if (!response.ok) {
      throw mobileHttpError(response.status, response.statusText, body);
    }
    return body as T;
  } catch (error) {
    if (error instanceof MobileApiError) {
      if (!ambiguousOnNetworkLoss || !error.retryable) throw error;
      throw new MobileApiError(error.message, error.category, error.status, false, error.actionId);
    }
    if (ambiguousOnNetworkLoss) {
      throw new MobileApiError(
        timedOut ? "Financial action outcome is unknown after timeout" : "Financial action outcome is unknown",
        "ambiguous_outcome",
        null,
        false,
      );
    }
    throw new MobileApiError(timedOut ? "Request timed out" : "Unable to reach CryptoARC", "connection", null, true);
  } finally {
    clearTimeout(timeoutId);
    options.signal?.removeEventListener("abort", onExternalAbort);
  }
}

export function mobileGet<T>(path: string, options: MobileGetOptions = {}): Promise<T> {
  return dispatch<T>(
    path,
    options,
    {
      method: "GET",
      headers: options.headers,
    },
    false,
  );
}

export function mobileAction<T, TBody = unknown>(path: string, options: MobileActionOptions<TBody>): Promise<T> {
  const idempotencyKey = options.idempotencyKey.trim();
  if (!idempotencyKey) {
    return Promise.reject(new MobileApiError("Idempotency key is required", "validation", null, false));
  }
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  headers.set("Idempotency-Key", idempotencyKey);
  return dispatch<T>(
    path,
    options,
    {
      method: options.method ?? "POST",
      body: JSON.stringify(options.body),
      headers,
    },
    true,
  );
}
