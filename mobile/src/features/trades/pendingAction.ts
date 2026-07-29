import * as SecureStore from "expo-secure-store";

const PENDING_ACTION_KEY = "cryptoarc.mobile.pending-action.v1";

export interface PendingMobileAction {
  actionId: string;
  entityId: string;
  actionType: string;
}

export interface PendingActionStore {
  load(): Promise<PendingMobileAction | null>;
  save(action: PendingMobileAction): Promise<void>;
  clear(actionId: string): Promise<void>;
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
    };
  } catch {
    return null;
  }
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
