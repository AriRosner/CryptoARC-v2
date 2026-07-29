import * as SecureStore from "expo-secure-store";

const PENDING_ACTION_KEY = "cryptoarc.mobile.pending-action.v1";

export interface PendingActionOwner {
  apiBaseUrl: string;
  deviceId: string;
  sessionId: string;
}

export interface PendingMobileAction {
  actionId: string;
  entityId: string;
  actionType: string;
  owner: PendingActionOwner | null;
  state: "pending" | "review_required";
  reviewMessage?: string;
}

export interface PendingActionStore {
  load(): Promise<PendingMobileAction | null>;
  save(action: PendingMobileAction): Promise<void>;
  clear(actionId: string): Promise<void>;
}

export const TEST_PENDING_ACTION_OWNER: PendingActionOwner = {
  apiBaseUrl: "test",
  deviceId: "test-device",
  sessionId: "test-session",
};

function parseOwner(value: unknown): PendingActionOwner | null {
  if (!value || typeof value !== "object") return null;
  const owner = value as Partial<PendingActionOwner>;
  if (
    typeof owner.apiBaseUrl !== "string" ||
    typeof owner.deviceId !== "string" ||
    typeof owner.sessionId !== "string" ||
    !owner.apiBaseUrl.trim() ||
    !owner.deviceId.trim() ||
    !owner.sessionId.trim()
  ) {
    return null;
  }
  return {
    apiBaseUrl: owner.apiBaseUrl.trim().replace(/\/+$/, "").toLowerCase(),
    deviceId: owner.deviceId.trim(),
    sessionId: owner.sessionId.trim(),
  };
}

function parsePendingAction(value: string | null): PendingMobileAction | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as Partial<PendingMobileAction>;
    if (
      typeof parsed.actionId !== "string" ||
      typeof parsed.entityId !== "string" ||
      typeof parsed.actionType !== "string" ||
      !parsed.actionId ||
      !parsed.entityId ||
      !parsed.actionType
    ) {
      return null;
    }
    return {
      actionId: parsed.actionId,
      entityId: parsed.entityId,
      actionType: parsed.actionType,
      owner: parseOwner(parsed.owner),
      state:
        parsed.state === "pending" || parsed.state === "review_required"
          ? parsed.state
          : parsed.owner
            ? "pending"
            : "review_required",
      reviewMessage:
        typeof parsed.reviewMessage === "string"
          ? parsed.reviewMessage
          : undefined,
    };
  } catch {
    return null;
  }
}

export function samePendingActionOwner(
  action: PendingMobileAction,
  owner: PendingActionOwner,
): boolean {
  const expected = parseOwner(owner);
  return Boolean(
    action.owner &&
      expected &&
      action.owner.apiBaseUrl === expected.apiBaseUrl &&
      action.owner.deviceId === expected.deviceId &&
      action.owner.sessionId === expected.sessionId,
  );
}

export function pendingActionForOwner(
  actionId: string,
  entityId: string,
  actionType: string,
  owner: PendingActionOwner,
): PendingMobileAction {
  return {
    actionId,
    entityId,
    actionType,
    owner: parseOwner(owner),
    state: "pending",
  };
}

export function pendingActionForReview(
  action: PendingMobileAction,
  reviewMessage: string,
): PendingMobileAction {
  return {
    ...action,
    state: "review_required",
    reviewMessage,
  };
}

export function pendingActionRoute(
  action: PendingMobileAction,
): string | null {
  const entityId = encodeURIComponent(action.entityId);
  if (["trade_approve", "trade_reject"].includes(action.actionType)) {
    return `/trade/${entityId}`;
  }
  if (
    ["position_adjust_exit", "position_close"].includes(action.actionType)
  ) {
    return `/position/${entityId}`;
  }
  if (
    ["withdrawal", "profit_sweep", "rent_recovery"].includes(
      action.actionType,
    )
  ) {
    return action.actionType === "withdrawal"
      ? "/wallet/withdraw"
      : `/wallet/treasury?action=${action.actionType}`;
  }
  return null;
}

export const pendingActionStore: PendingActionStore = {
  async load() {
    return parsePendingAction(
      await SecureStore.getItemAsync(PENDING_ACTION_KEY),
    );
  },
  async save(action) {
    await SecureStore.setItemAsync(
      PENDING_ACTION_KEY,
      JSON.stringify(action),
    );
  },
  async clear(actionId) {
    const current = parsePendingAction(
      await SecureStore.getItemAsync(PENDING_ACTION_KEY),
    );
    if (current?.actionId === actionId) {
      await SecureStore.deleteItemAsync(PENDING_ACTION_KEY);
    }
  },
};
