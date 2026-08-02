import * as Crypto from "expo-crypto";

import {
  mobileAction,
  mobileGet,
  type MobileGetOptions,
} from "../../core/api/client";
import type {
  MobileAlertsPayload,
  PushRegistrationContext,
} from "./types";

export function fetchAlerts(
  options?: MobileGetOptions,
): Promise<MobileAlertsPayload> {
  return mobileGet<MobileAlertsPayload>("/api/mobile/alerts", options);
}

export function acknowledgeAlert(
  eventId: string,
  options: MobileGetOptions = {},
): Promise<{
  event_id: string;
  acknowledged: boolean;
  acknowledged_at: string;
}> {
  return mobileAction(
    `/api/mobile/alerts/${encodeURIComponent(eventId)}/acknowledge`,
    {
      ...options,
      body: {},
      idempotencyKey: `alert-ack-${eventId}`,
    },
  );
}

export async function registerPushToken(
  rawToken: string,
  context: PushRegistrationContext,
): Promise<void> {
  await mobileAction("/api/mobile/notifications/register", {
    apiBaseUrl: context.apiBaseUrl,
    token: context.token,
    body: { token: rawToken, platform: "android" },
    idempotencyKey: `push-register-${context.generation}-${Crypto.randomUUID()}`,
  });
}

export async function unregisterPushToken(
  options: MobileGetOptions = {},
): Promise<void> {
  await mobileAction("/api/mobile/notifications/unregister", {
    ...options,
    body: {},
    idempotencyKey: `push-unregister-${Crypto.randomUUID()}`,
  });
}

export async function validateNotificationDestination(
  route: string,
  options: MobileGetOptions,
): Promise<void> {
  const match = /^\/(trade|position)\/([A-Za-z0-9][A-Za-z0-9_-]{0,119})$/.exec(
    route,
  );
  if (!match) return;
  const collection = match[1] === "trade" ? "trades" : "positions";
  await mobileGet(
    `/api/mobile/${collection}/${encodeURIComponent(match[2])}`,
    options,
  );
}
