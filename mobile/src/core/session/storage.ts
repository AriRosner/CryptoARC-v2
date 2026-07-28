import * as SecureStore from "expo-secure-store";

import type { MobileDevice } from "../../types";
import type { SecureSessionRecord } from "./types";

export const SESSION_STORAGE_KEY = "cryptoarc.mobile.session.v2";
export const LEGACY_TOKEN_KEY = "cryptoarc.mobile.token";
export const LEGACY_API_BASE_KEY = "cryptoarc.mobile.apiBaseUrl";
export const LEGACY_DEVICE_KEY = "cryptoarc.mobile.device";

interface SecureStoreApi {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
  deleteItemAsync(key: string): Promise<void>;
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

async function cleanupLegacyKeys(secureStore: SecureStoreApi): Promise<void> {
  await Promise.allSettled([
    secureStore.deleteItemAsync(LEGACY_API_BASE_KEY),
    secureStore.deleteItemAsync(LEGACY_TOKEN_KEY),
    secureStore.deleteItemAsync(LEGACY_DEVICE_KEY),
  ]);
}

export function createSecureSessionStorage(
  secureStore: SecureStoreApi = SecureStore,
  now: () => string = () => new Date().toISOString(),
) {
  const save = async (record: SecureSessionRecord): Promise<void> => {
    const serialized = JSON.stringify(record);
    const previous = await secureStore.getItemAsync(SESSION_STORAGE_KEY);
    try {
      parseSecureSessionRecord(serialized);
      await secureStore.setItemAsync(SESSION_STORAGE_KEY, serialized);
      const verified = await secureStore.getItemAsync(SESSION_STORAGE_KEY);
      if (!sameRecord(verified, record)) throw new Error("Secure session verification failed");
    } catch (error) {
      if (previous === null) {
        await secureStore.deleteItemAsync(SESSION_STORAGE_KEY).catch(() => undefined);
      } else {
        await secureStore.setItemAsync(SESSION_STORAGE_KEY, previous).catch(() => undefined);
      }
      throw error;
    }
  };

  const loadOrMigrate = async (): Promise<SecureSessionRecord | null> => {
    const current = await secureStore.getItemAsync(SESSION_STORAGE_KEY);
    if (current !== null) {
      const record = parseSecureSessionRecord(current);
      await cleanupLegacyKeys(secureStore);
      return record;
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
    await cleanupLegacyKeys(secureStore);
    return migrated;
  };

  const clear = async (): Promise<void> => {
    await secureStore.deleteItemAsync(SESSION_STORAGE_KEY);
  };

  return { clear, loadOrMigrate, save };
}

export const secureSessionStorage = createSecureSessionStorage();
