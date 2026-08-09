import * as Crypto from "expo-crypto";

import {
  mobileAction,
  mobileGet,
  type MobileActionOptions,
  type MobileGetOptions,
} from "../../core/api/client";
import type {
  GuardedApprovalInput,
  MobileActionReceipt,
  MobileTradeDetail,
  MobileTradeDraft,
  MobileTradesPayload,
  MobileTradeValidation,
} from "./types";

type ActionConnectionOptions = Pick<
  MobileActionOptions<unknown>,
  "apiBaseUrl" | "token" | "timeoutMs" | "signal" | "headers"
>;

function guardedBody(input: Omit<GuardedApprovalInput, "idempotencyKey">) {
  return {
    expected_version: input.expectedVersion,
    draft: input.draft,
    escalation_acknowledged: input.escalationAcknowledged,
  };
}

export function createMobileIdempotencyKey(): string {
  return `mobile-${Crypto.randomUUID()}`;
}

export function fetchTrades(
  options?: MobileGetOptions,
): Promise<MobileTradesPayload> {
  return mobileGet<MobileTradesPayload>("/api/mobile/trades", options);
}

export function fetchTrade(
  intentId: string,
  options?: MobileGetOptions,
): Promise<MobileTradeDetail> {
  return mobileGet<MobileTradeDetail>(
    `/api/mobile/trades/${encodeURIComponent(intentId)}`,
    options,
  );
}

export function validateTrade(
  intentId: string,
  input: Omit<GuardedApprovalInput, "idempotencyKey">,
  options: ActionConnectionOptions = {},
): Promise<MobileTradeValidation> {
  return mobileAction<MobileTradeValidation, ReturnType<typeof guardedBody>>(
    `/api/mobile/trades/${encodeURIComponent(intentId)}/validate`,
    {
      ...options,
      body: guardedBody(input),
      idempotencyKey: `validate-${intentId}-${input.expectedVersion}`,
    },
  );
}

export function approveTrade(
  intentId: string,
  input: GuardedApprovalInput,
  options: ActionConnectionOptions = {},
): Promise<MobileActionReceipt> {
  return mobileAction<MobileActionReceipt, ReturnType<typeof guardedBody>>(
    `/api/mobile/trades/${encodeURIComponent(intentId)}/approve`,
    {
      ...options,
      body: guardedBody(input),
      idempotencyKey: input.idempotencyKey,
    },
  );
}

export function rejectTrade(
  intentId: string,
  input: {
    expectedVersion: number;
    reason: string;
    idempotencyKey: string;
  },
  options: ActionConnectionOptions = {},
): Promise<MobileActionReceipt> {
  return mobileAction<
    MobileActionReceipt,
    { expected_version: number; reason: string }
  >(`/api/mobile/trades/${encodeURIComponent(intentId)}/reject`, {
    ...options,
    body: {
      expected_version: input.expectedVersion,
      reason: input.reason,
    },
    idempotencyKey: input.idempotencyKey,
  });
}

export function adjustPositionExit(
  positionId: string,
  input: {
    expectedVersion: number;
    stopPct: string;
    targetPct: string;
    escalationAcknowledged: boolean;
    idempotencyKey: string;
  },
  options: ActionConnectionOptions = {},
): Promise<MobileActionReceipt> {
  return mobileAction<
    MobileActionReceipt,
    {
      expected_version: number;
      stop_pct: string;
      target_pct: string;
      escalation_acknowledged: boolean;
    }
  >(`/api/mobile/positions/${encodeURIComponent(positionId)}/adjust-exit`, {
    ...options,
    body: {
      expected_version: input.expectedVersion,
      stop_pct: input.stopPct,
      target_pct: input.targetPct,
      escalation_acknowledged: input.escalationAcknowledged,
    },
    idempotencyKey: input.idempotencyKey,
  });
}

export function closePosition(
  positionId: string,
  input: GuardedApprovalInput & {
    intentId: string;
    positionVersion: number;
  },
  options: ActionConnectionOptions = {},
): Promise<MobileActionReceipt> {
  return mobileAction<
    MobileActionReceipt,
    {
      expected_version: number;
      position_version: number;
      intent_id: string;
      draft: MobileTradeDraft;
      escalation_acknowledged: boolean;
    }
  >(`/api/mobile/positions/${encodeURIComponent(positionId)}/close`, {
    ...options,
    body: {
      expected_version: input.expectedVersion,
      position_version: input.positionVersion,
      intent_id: input.intentId,
      draft: input.draft,
      escalation_acknowledged: input.escalationAcknowledged,
    },
    idempotencyKey: input.idempotencyKey,
  });
}

export function fetchAction(
  actionId: string,
  options?: MobileGetOptions,
): Promise<MobileActionReceipt> {
  return mobileGet<MobileActionReceipt>(
    `/api/mobile/actions/${encodeURIComponent(actionId)}`,
    options,
  );
}
