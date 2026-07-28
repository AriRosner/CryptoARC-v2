import * as SecureStore from "expo-secure-store";

import type { MobileDevice } from "../../types";
import type { SecureSessionRecord } from "./types";

export const SESSION_STORAGE_KEY = "cryptoarc.mobile.session.v2";
export const SESSION_CONTROL_KEY = "cryptoarc.mobile.session.control.v1";
export const SESSION_SLOT_A_KEY = SESSION_STORAGE_KEY;
export const SESSION_SLOT_B_KEY = "cryptoarc.mobile.session.slot-b.v1";
export const LEGACY_TOKEN_KEY = "cryptoarc.mobile.token";
export const LEGACY_API_BASE_KEY = "cryptoarc.mobile.apiBaseUrl";
export const LEGACY_DEVICE_KEY = "cryptoarc.mobile.device";

type SessionSlot = "a" | "b";

interface ActiveSessionControl {
  version: 1;
  status: "active";
  generation: number;
  slot: SessionSlot;
  savedAt: string;
}

interface ClearedSessionControl {
  version: 1;
  status: "cleared";
  generation: number;
  savedAt: string;
}

type SessionControl = ActiveSessionControl | ClearedSessionControl;

interface SecureStoreApi {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
  deleteItemAsync(key: string): Promise<void>;
}

export class SecureSessionRollbackError extends Error {
  constructor() {
    super("Secure session rollback failed");
  }
}

function validDevice(value: unknown): value is MobileDevice {
  if (!value || typeof value !== "object") return false;
  const device = value as Partial<MobileDevice>;
  return (
    typeof device.id === "string" &&
    device.id.length > 0 &&
    typeof device.name === "string" &&
    typeof device.platform === "string" &&
    Array.isArray(device.scopes) &&
    device.scopes.every((scope) => typeof scope === "string") &&
    typeof device.created_at === "string" &&
    typeof device.last_seen_at === "string" &&
    typeof device.expires_at === "string" &&
    typeof device.revoked_at === "string"
  );
}

export function parseSecureSessionRecord(raw: string): SecureSessionRecord {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("Secure session record is invalid");
  }
  if (!value || typeof value !== "object") throw new Error("Secure session record is invalid");
  const record = value as Partial<SecureSessionRecord>;
  if (
    record.version !== 2 ||
    typeof record.apiBaseUrl !== "string" ||
    !record.apiBaseUrl.trim() ||
    typeof record.token !== "string" ||
    !record.token ||
    !validDevice(record.device) ||
    typeof record.savedAt !== "string" ||
    !record.savedAt ||
    !Number.isFinite(Date.parse(record.savedAt))
  ) {
    throw new Error("Secure session record is invalid");
  }
  return record as SecureSessionRecord;
}

function sameRecord(raw: string | null, expected: SecureSessionRecord): boolean {
  if (raw === null) return false;
  try {
    return JSON.stringify(parseSecureSessionRecord(raw)) === JSON.stringify(expected);
  } catch {
    return false;
  }
}

function parseSessionControl(raw: string): SessionControl {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("Secure session control record is invalid");
  }
  if (!value || typeof value !== "object") {
    throw new Error("Secure session control record is invalid");
  }
  const control = value as Partial<SessionControl>;
  if (
    control.version !== 1 ||
    !Number.isInteger(control.generation) ||
    Number(control.generation) < 1 ||
    typeof control.savedAt !== "string" ||
    !Number.isFinite(Date.parse(control.savedAt))
  ) {
    throw new Error("Secure session control record is invalid");
  }
  if (control.status === "cleared") return control as ClearedSessionControl;
  if (control.status === "active" && (control.slot === "a" || control.slot === "b")) {
    return control as ActiveSessionControl;
  }
  throw new Error("Secure session control record is invalid");
}

function slotKey(slot: SessionSlot): string {
  return slot === "a" ? SESSION_SLOT_A_KEY : SESSION_SLOT_B_KEY;
}

async function cleanupKeys(secureStore: SecureStoreApi, keys: string[]): Promise<void> {
  await Promise.allSettled([
    ...[...new Set(keys)].map((key) => secureStore.deleteItemAsync(key)),
  ]);
}

export function createSecureSessionStorage(
  secureStore: SecureStoreApi = SecureStore,
  now: () => string = () => new Date().toISOString(),
) {
  const verifyControl = async (expectedRaw: string): Promise<void> => {
    const persisted = await secureStore.getItemAsync(SESSION_CONTROL_KEY);
    if (persisted !== expectedRaw) throw new Error("Secure session control verification failed");
    parseSessionControl(persisted);
  };

  const writeControl = async (control: SessionControl): Promise<string> => {
    const serialized = JSON.stringify(control);
    await secureStore.setItemAsync(SESSION_CONTROL_KEY, serialized);
    await verifyControl(serialized);
    return serialized;
  };

  const writeSlot = async (slot: SessionSlot, record: SecureSessionRecord): Promise<void> => {
    const serialized = JSON.stringify(record);
    parseSecureSessionRecord(serialized);
    const key = slotKey(slot);
    await secureStore.setItemAsync(key, serialized);
    const persisted = await secureStore.getItemAsync(key);
    if (!sameRecord(persisted, record)) throw new Error("Secure session verification failed");
  };

  const writeTombstone = async (generation: number): Promise<void> => {
    await writeControl({
      version: 1,
      status: "cleared",
      generation,
      savedAt: now(),
    });
  };

  const restoreControl = async (previousRaw: string | null): Promise<void> => {
    if (previousRaw === null) {
      await secureStore.deleteItemAsync(SESSION_CONTROL_KEY);
      if ((await secureStore.getItemAsync(SESSION_CONTROL_KEY)) !== null) {
        throw new Error("Secure session rollback delete verification failed");
      }
      return;
    }
    await secureStore.setItemAsync(SESSION_CONTROL_KEY, previousRaw);
    await verifyControl(previousRaw);
  };

  const bootstrapStandaloneRecord = async (
    record: SecureSessionRecord,
  ): Promise<{ control: ActiveSessionControl; raw: string }> => {
    const control: ActiveSessionControl = {
      version: 1,
      status: "active",
      generation: 1,
      slot: "a",
      savedAt: record.savedAt,
    };
    const raw = await writeControl(control);
    return { control, raw };
  };

  const save = async (record: SecureSessionRecord): Promise<void> => {
    parseSecureSessionRecord(JSON.stringify(record));
    let previousRaw = await secureStore.getItemAsync(SESSION_CONTROL_KEY);
    let previousControl: SessionControl | null = previousRaw
      ? parseSessionControl(previousRaw)
      : null;

    if (previousControl === null) {
      const standalone = await secureStore.getItemAsync(SESSION_SLOT_A_KEY);
      if (standalone !== null) {
        const bootstrapped = await bootstrapStandaloneRecord(parseSecureSessionRecord(standalone));
        previousControl = bootstrapped.control;
        previousRaw = bootstrapped.raw;
      } else {
        const initialAuthority: ClearedSessionControl = {
          version: 1,
          status: "cleared",
          generation: 1,
          savedAt: now(),
        };
        previousRaw = await writeControl(initialAuthority);
        previousControl = initialAuthority;
      }
    }

    const targetSlot: SessionSlot =
      previousControl?.status === "active" && previousControl.slot === "a" ? "b" : "a";
    const nextGeneration = (previousControl?.generation ?? 0) + 1;
    const nextControl: ActiveSessionControl = {
      version: 1,
      status: "active",
      generation: nextGeneration,
      slot: targetSlot,
      savedAt: record.savedAt,
    };

    try {
      await writeSlot(targetSlot, record);
    } catch (error) {
      try {
        const targetKey = slotKey(targetSlot);
        await secureStore.deleteItemAsync(targetKey);
        if ((await secureStore.getItemAsync(targetKey)) !== null) {
          throw new Error("Secure session slot rollback verification failed");
        }
      } catch {
        if (previousRaw !== null) {
          try {
            await verifyControl(previousRaw);
          } catch {
            try {
              await writeTombstone(nextGeneration + 1);
            } catch {
              // No further persistence fallback exists; the caller must quarantine memory.
            }
            throw new SecureSessionRollbackError();
          }
        } else {
          try {
            await writeTombstone(nextGeneration + 1);
          } catch {
            // No further persistence fallback exists; the caller must quarantine memory.
          }
          throw new SecureSessionRollbackError();
        }
      }
      throw error;
    }
    try {
      await writeControl(nextControl);
    } catch (error) {
      try {
        await restoreControl(previousRaw);
      } catch {
        try {
          await writeTombstone(nextGeneration + 1);
        } catch {
          // No further persistence fallback exists; the caller must quarantine memory.
        }
        await cleanupKeys(secureStore, [slotKey(targetSlot)]);
        throw new SecureSessionRollbackError();
      }
      await cleanupKeys(secureStore, [slotKey(targetSlot)]);
      throw error;
    }
  };

  const loadControlled = async (control: SessionControl): Promise<SecureSessionRecord | null> => {
    if (control.status === "cleared") {
      await cleanupKeys(secureStore, [
        SESSION_SLOT_A_KEY,
        SESSION_SLOT_B_KEY,
        LEGACY_API_BASE_KEY,
        LEGACY_TOKEN_KEY,
        LEGACY_DEVICE_KEY,
      ]);
      return null;
    }
    const raw = await secureStore.getItemAsync(slotKey(control.slot));
    if (raw === null) throw new Error("Secure session credential slot is missing");
    const record = parseSecureSessionRecord(raw);
    if (record.savedAt !== control.savedAt) {
      throw new Error("Secure session generation does not match credential slot");
    }
    await cleanupKeys(secureStore, [
      LEGACY_API_BASE_KEY,
      LEGACY_TOKEN_KEY,
      LEGACY_DEVICE_KEY,
    ]);
    return record;
  };

  const loadOrMigrate = async (): Promise<SecureSessionRecord | null> => {
    const controlRaw = await secureStore.getItemAsync(SESSION_CONTROL_KEY);
    if (controlRaw !== null) {
      return loadControlled(parseSessionControl(controlRaw));
    }

    const standalone = await secureStore.getItemAsync(SESSION_SLOT_A_KEY);
    if (standalone !== null) {
      const record = parseSecureSessionRecord(standalone);
      const bootstrapped = await bootstrapStandaloneRecord(record);
      await cleanupKeys(secureStore, [
        LEGACY_API_BASE_KEY,
        LEGACY_TOKEN_KEY,
        LEGACY_DEVICE_KEY,
      ]);
      return loadControlled(bootstrapped.control);
    }

    const [apiBaseUrl, token, rawDevice] = await Promise.all([
      secureStore.getItemAsync(LEGACY_API_BASE_KEY),
      secureStore.getItemAsync(LEGACY_TOKEN_KEY),
      secureStore.getItemAsync(LEGACY_DEVICE_KEY),
    ]);
    if (apiBaseUrl === null && token === null && rawDevice === null) return null;
    if (!apiBaseUrl || !token || !rawDevice) throw new Error("Legacy secure session is incomplete");

    let device: unknown;
    try {
      device = JSON.parse(rawDevice);
    } catch {
      throw new Error("Legacy secure session is invalid");
    }
    if (!validDevice(device)) throw new Error("Legacy secure session is invalid");

    const migrated: SecureSessionRecord = {
      version: 2,
      apiBaseUrl,
      token,
      device,
      savedAt: now(),
    };
    await save(migrated);
    await cleanupKeys(secureStore, [
      LEGACY_API_BASE_KEY,
      LEGACY_TOKEN_KEY,
      LEGACY_DEVICE_KEY,
    ]);
    return migrated;
  };

  const clear = async (): Promise<void> => {
    const controlRaw = await secureStore.getItemAsync(SESSION_CONTROL_KEY);
    const generation = controlRaw === null ? 0 : parseSessionControl(controlRaw).generation;
    await writeTombstone(generation + 1);
    await cleanupKeys(secureStore, [
      SESSION_SLOT_A_KEY,
      SESSION_SLOT_B_KEY,
      LEGACY_API_BASE_KEY,
      LEGACY_TOKEN_KEY,
      LEGACY_DEVICE_KEY,
    ]);
  };

  return { clear, loadOrMigrate, save };
}

export const secureSessionStorage = createSecureSessionStorage();
