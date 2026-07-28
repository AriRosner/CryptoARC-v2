import type { MobileDevice } from "../../types";
import {
  LEGACY_API_BASE_KEY,
  LEGACY_DEVICE_KEY,
  LEGACY_TOKEN_KEY,
  SESSION_CONTROL_KEY,
  SESSION_SLOT_A_KEY,
  SESSION_SLOT_B_KEY,
  SESSION_STORAGE_KEY,
  createSecureSessionStorage,
} from "../session/storage";
import type { SecureSessionRecord } from "../session/types";

const device: MobileDevice = {
  id: "mobile-1",
  name: "Operator phone",
  platform: "android",
  scopes: ["mobile:monitor"],
  created_at: "2026-07-28T10:00:00.000Z",
  last_seen_at: "2026-07-28T10:00:00.000Z",
  expires_at: "2026-08-28T10:00:00.000Z",
  revoked_at: "",
};

const record: SecureSessionRecord = {
  version: 2,
  apiBaseUrl: "https://cryptoarc.test",
  token: "mobile-token",
  device,
  savedAt: "2026-07-28T10:00:00.000Z",
};

function secureStoreFixture(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  const operations: string[] = [];
  return {
    values,
    operations,
    secureStore: {
      getItemAsync: jest.fn(async (key: string) => {
        operations.push(`get:${key}`);
        return values.get(key) ?? null;
      }),
      setItemAsync: jest.fn(async (key: string, value: string) => {
        operations.push(`set:${key}`);
        values.set(key, value);
      }),
      deleteItemAsync: jest.fn(async (key: string) => {
        operations.push(`delete:${key}`);
        values.delete(key);
      }),
    },
  };
}

describe("atomic secure session storage", () => {
  it("migrates the legacy keys to one verified v2 record and survives remount", async () => {
    const fixture = secureStoreFixture({
      [LEGACY_API_BASE_KEY]: record.apiBaseUrl,
      [LEGACY_TOKEN_KEY]: record.token,
      [LEGACY_DEVICE_KEY]: JSON.stringify(record.device),
    });
    const storage = createSecureSessionStorage(fixture.secureStore, () => record.savedAt);

    await expect(storage.loadOrMigrate()).resolves.toEqual(record);

    const writeIndex = fixture.operations.indexOf(`set:${SESSION_STORAGE_KEY}`);
    const verifyIndex = fixture.operations.indexOf(`get:${SESSION_STORAGE_KEY}`, writeIndex + 1);
    const firstDeleteIndex = fixture.operations.findIndex((operation) => operation.startsWith("delete:"));
    expect(writeIndex).toBeGreaterThan(-1);
    expect(verifyIndex).toBeGreaterThan(writeIndex);
    expect(firstDeleteIndex).toBeGreaterThan(verifyIndex);
    expect(fixture.values.has(LEGACY_API_BASE_KEY)).toBe(false);
    expect(fixture.values.has(LEGACY_TOKEN_KEY)).toBe(false);
    expect(fixture.values.has(LEGACY_DEVICE_KEY)).toBe(false);

    const remountedStorage = createSecureSessionStorage(fixture.secureStore, () => "later");
    await expect(remountedStorage.loadOrMigrate()).resolves.toEqual(record);
    expect(fixture.values.get(SESSION_STORAGE_KEY)).toBe(JSON.stringify(record));
  });

  it("does not delete any legacy key when the v2 write cannot be verified", async () => {
    const fixture = secureStoreFixture({
      [LEGACY_API_BASE_KEY]: record.apiBaseUrl,
      [LEGACY_TOKEN_KEY]: record.token,
      [LEGACY_DEVICE_KEY]: JSON.stringify(record.device),
    });
    fixture.secureStore.getItemAsync.mockImplementation(async (key: string) => {
      fixture.operations.push(`get:${key}`);
      if (key === SESSION_STORAGE_KEY && fixture.values.has(key)) return JSON.stringify({ version: 1 });
      return fixture.values.get(key) ?? null;
    });
    const storage = createSecureSessionStorage(fixture.secureStore, () => record.savedAt);

    await expect(storage.loadOrMigrate()).rejects.toThrow("Secure session verification failed");
    expect(fixture.values.get(LEGACY_API_BASE_KEY)).toBe(record.apiBaseUrl);
    expect(fixture.values.get(LEGACY_TOKEN_KEY)).toBe(record.token);
    expect(fixture.values.get(LEGACY_DEVICE_KEY)).toBe(JSON.stringify(record.device));
    expect(fixture.secureStore.deleteItemAsync).not.toHaveBeenCalledWith(LEGACY_API_BASE_KEY);
    expect(fixture.secureStore.deleteItemAsync).not.toHaveBeenCalledWith(LEGACY_TOKEN_KEY);
    expect(fixture.secureStore.deleteItemAsync).not.toHaveBeenCalledWith(LEGACY_DEVICE_KEY);
  });

  it("does not bootstrap an uncommitted first-save slot after verification fails", async () => {
    const fixture = secureStoreFixture();
    let corruptFirstSlotVerification = true;
    fixture.secureStore.getItemAsync.mockImplementation(async (key: string) => {
      fixture.operations.push(`get:${key}`);
      if (
        key === SESSION_SLOT_A_KEY &&
        fixture.values.has(key) &&
        corruptFirstSlotVerification
      ) {
        corruptFirstSlotVerification = false;
        return JSON.stringify({ version: 1 });
      }
      return fixture.values.get(key) ?? null;
    });
    const storage = createSecureSessionStorage(fixture.secureStore);

    await expect(storage.save(record)).rejects.toThrow("Secure session verification failed");

    await expect(
      createSecureSessionStorage(fixture.secureStore).loadOrMigrate(),
    ).resolves.toBeNull();
  });

  it("restores the previous v2 record when a replacement write cannot be verified", async () => {
    const fixture = secureStoreFixture({ [SESSION_STORAGE_KEY]: JSON.stringify(record) });
    const replacement = { ...record, token: "replacement-token", savedAt: "2026-07-28T11:00:00.000Z" };
    fixture.secureStore.getItemAsync.mockImplementation(async (key: string) => {
      fixture.operations.push(`get:${key}`);
      if (key === SESSION_SLOT_B_KEY && fixture.values.has(key)) {
        return JSON.stringify({ version: 1 });
      }
      return fixture.values.get(key) ?? null;
    });
    const storage = createSecureSessionStorage(fixture.secureStore);

    await expect(storage.save(replacement)).rejects.toThrow("Secure session verification failed");
    expect(fixture.values.get(SESSION_STORAGE_KEY)).toBe(JSON.stringify(record));
  });

  it("fails closed on a malformed v2 record instead of recovering from legacy tokens", async () => {
    const fixture = secureStoreFixture({
      [SESSION_STORAGE_KEY]: JSON.stringify({ ...record, version: 1 }),
      [LEGACY_API_BASE_KEY]: record.apiBaseUrl,
      [LEGACY_TOKEN_KEY]: record.token,
      [LEGACY_DEVICE_KEY]: JSON.stringify(record.device),
    });
    const storage = createSecureSessionStorage(fixture.secureStore);

    await expect(storage.loadOrMigrate()).rejects.toThrow("Secure session record is invalid");
    expect(fixture.secureStore.setItemAsync).not.toHaveBeenCalled();
    expect(fixture.secureStore.deleteItemAsync).not.toHaveBeenCalled();
  });

  it("commits a credential-free tombstone before cleanup so failed legacy deletes cannot resurrect a session", async () => {
    const fixture = secureStoreFixture({
      [LEGACY_API_BASE_KEY]: record.apiBaseUrl,
      [LEGACY_TOKEN_KEY]: record.token,
      [LEGACY_DEVICE_KEY]: JSON.stringify(record.device),
    });
    fixture.secureStore.deleteItemAsync.mockImplementation(async (key: string) => {
      fixture.operations.push(`delete:${key}`);
      if (key === LEGACY_TOKEN_KEY || key === LEGACY_DEVICE_KEY) {
        throw new Error("legacy cleanup interrupted");
      }
      fixture.values.delete(key);
    });
    const storage = createSecureSessionStorage(fixture.secureStore, () => record.savedAt);

    await expect(storage.loadOrMigrate()).resolves.toEqual(record);
    expect(fixture.values.get(LEGACY_TOKEN_KEY)).toBe(record.token);

    await expect(storage.clear()).resolves.toBeUndefined();

    const tombstone = fixture.values.get(SESSION_CONTROL_KEY);
    expect(tombstone).toBeDefined();
    expect(tombstone).not.toContain(record.token);
    expect(tombstone).not.toContain(record.apiBaseUrl);
    await expect(createSecureSessionStorage(fixture.secureStore).loadOrMigrate()).resolves.toBeNull();
  });

  it("remains cleared after partial migration cleanup and interrupted credential-slot deletion", async () => {
    const fixture = secureStoreFixture({
      [LEGACY_API_BASE_KEY]: record.apiBaseUrl,
      [LEGACY_TOKEN_KEY]: record.token,
      [LEGACY_DEVICE_KEY]: JSON.stringify(record.device),
    });
    fixture.secureStore.deleteItemAsync.mockImplementation(async (key: string) => {
      fixture.operations.push(`delete:${key}`);
      if (key === SESSION_SLOT_A_KEY || key === SESSION_SLOT_B_KEY || key === LEGACY_TOKEN_KEY) {
        throw new Error("process interrupted during cleanup");
      }
      fixture.values.delete(key);
    });
    const storage = createSecureSessionStorage(fixture.secureStore, () => record.savedAt);
    await storage.loadOrMigrate();

    await expect(storage.clear()).resolves.toBeUndefined();
    expect(
      [SESSION_SLOT_A_KEY, SESSION_SLOT_B_KEY].some((key) => fixture.values.has(key)),
    ).toBe(true);
    expect(fixture.values.has(LEGACY_TOKEN_KEY)).toBe(true);
    await expect(createSecureSessionStorage(fixture.secureStore).loadOrMigrate()).resolves.toBeNull();
  });

  it("fails closed behind a tombstone when replacement-control rollback restore fails", async () => {
    const fixture = secureStoreFixture();
    const storage = createSecureSessionStorage(fixture.secureStore, () => record.savedAt);
    await storage.save(record);
    const previousControl = fixture.values.get(SESSION_CONTROL_KEY);
    expect(previousControl).toBeDefined();

    const replacement = { ...record, token: "replacement-token", savedAt: "2026-07-28T11:00:00.000Z" };
    let corruptNextControlRead = false;
    fixture.secureStore.getItemAsync.mockImplementation(async (key: string) => {
      fixture.operations.push(`get:${key}`);
      if (key === SESSION_CONTROL_KEY && corruptNextControlRead) {
        corruptNextControlRead = false;
        return JSON.stringify({ version: 999 });
      }
      return fixture.values.get(key) ?? null;
    });
    fixture.secureStore.setItemAsync.mockImplementation(async (key: string, value: string) => {
      fixture.operations.push(`set:${key}`);
      if (
        key === SESSION_CONTROL_KEY &&
        value !== previousControl &&
        JSON.parse(value).status === "active"
      ) {
        fixture.values.set(key, value);
        corruptNextControlRead = true;
        return;
      }
      if (key === SESSION_CONTROL_KEY && value === previousControl) {
        throw new Error("rollback restore failed");
      }
      fixture.values.set(key, value);
    });

    await expect(storage.save(replacement)).rejects.toThrow("Secure session rollback failed");

    const control = fixture.values.get(SESSION_CONTROL_KEY);
    expect(control).not.toContain(replacement.token);
    await expect(createSecureSessionStorage(fixture.secureStore).loadOrMigrate()).resolves.toBeNull();
  });

  it("fails closed behind a tombstone when first-save rollback delete fails", async () => {
    const fixture = secureStoreFixture();
    const storage = createSecureSessionStorage(fixture.secureStore, () => record.savedAt);
    let corruptNextControlRead = false;
    fixture.secureStore.getItemAsync.mockImplementation(async (key: string) => {
      fixture.operations.push(`get:${key}`);
      if (key === SESSION_CONTROL_KEY && corruptNextControlRead) {
        corruptNextControlRead = false;
        return JSON.stringify({ version: 999 });
      }
      return fixture.values.get(key) ?? null;
    });
    fixture.secureStore.setItemAsync.mockImplementation(async (key: string, value: string) => {
      fixture.operations.push(`set:${key}`);
      fixture.values.set(key, value);
      if (key === SESSION_CONTROL_KEY && JSON.parse(value).status === "active") {
        corruptNextControlRead = true;
      }
    });
    fixture.secureStore.deleteItemAsync.mockImplementation(async (key: string) => {
      fixture.operations.push(`delete:${key}`);
      if (key === SESSION_CONTROL_KEY) throw new Error("rollback delete failed");
      fixture.values.delete(key);
    });

    await expect(storage.save(record)).rejects.toThrow("Secure session rollback failed");

    const control = fixture.values.get(SESSION_CONTROL_KEY);
    expect(control).not.toContain(record.token);
    await expect(createSecureSessionStorage(fixture.secureStore).loadOrMigrate()).resolves.toBeNull();
  });
});
