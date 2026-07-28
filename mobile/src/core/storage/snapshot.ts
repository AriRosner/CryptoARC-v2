import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import * as SQLite from "expo-sqlite";

export interface VerifiedSnapshot<T> {
  schemaVersion: 1;
  verifiedAt: string;
  serverTime: string;
  sequence: number;
  payload: T;
}

const SNAPSHOT_KEY_STORAGE_KEY = "cryptoarc.mobile.snapshot.sqlcipher-key.v1";
const SNAPSHOT_DATABASE_NAME = "cryptoarc-mobile-snapshot.db";
const PROHIBITED_FIELDS = new Set([
  "access_token",
  "accesstoken",
  "auth_token",
  "authtoken",
  "bearer_token",
  "bearertoken",
  "credential",
  "mnemonic",
  "password",
  "private_key",
  "privatekey",
  "refresh_token",
  "refreshtoken",
  "secret",
  "seed",
  "seed_phrase",
  "seedphrase",
  "session_token",
  "sessiontoken",
  "signature",
]);

interface SnapshotDatabase {
  execAsync(source: string): Promise<void>;
  getFirstAsync(source: string, ...params: unknown[]): Promise<{ value: string } | null>;
  runAsync(source: string, ...params: unknown[]): Promise<unknown>;
}

interface SnapshotDependencies {
  crypto: {
    getRandomBytesAsync(byteCount: number): Promise<Uint8Array>;
  };
  secureStore: {
    getItemAsync(key: string): Promise<string | null>;
    setItemAsync(key: string, value: string): Promise<void>;
  };
  sqlite: {
    openDatabaseAsync(name: string): Promise<SnapshotDatabase>;
  };
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function assertReadModel(value: unknown, seen = new Set<object>()): void {
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("Snapshot payload must be JSON-safe");
    return;
  }
  if (typeof value !== "object") throw new Error("Snapshot payload must be a read model");
  if (seen.has(value)) throw new Error("Snapshot payload must not contain cycles");
  seen.add(value);
  if (Array.isArray(value)) {
    value.forEach((item) => assertReadModel(item, seen));
  } else {
    for (const [key, item] of Object.entries(value)) {
      const normalized = key.toLowerCase().replace(/-/g, "_");
      if (PROHIBITED_FIELDS.has(normalized)) {
        throw new Error(`Snapshot payload contains prohibited field: ${key}`);
      }
      assertReadModel(item, seen);
    }
  }
  seen.delete(value);
}

function assertSnapshot<T>(snapshot: VerifiedSnapshot<T>): void {
  if (
    snapshot.schemaVersion !== 1 ||
    !Number.isFinite(Date.parse(snapshot.verifiedAt)) ||
    !Number.isFinite(Date.parse(snapshot.serverTime)) ||
    !Number.isInteger(snapshot.sequence) ||
    snapshot.sequence < 0
  ) {
    throw new Error("Verified snapshot metadata is invalid");
  }
  assertReadModel(snapshot.payload);
}

export function createSnapshotStorage(dependencies: SnapshotDependencies = {
  crypto: Crypto,
  secureStore: SecureStore,
  sqlite: SQLite,
}) {
  let databasePromise: Promise<SnapshotDatabase> | null = null;
  let keyPromise: Promise<string> | null = null;

  const getOrCreateKey = async (): Promise<string> => {
    const existing = await dependencies.secureStore.getItemAsync(SNAPSHOT_KEY_STORAGE_KEY);
    if (existing !== null) {
      if (!/^[a-f0-9]{64}$/.test(existing)) throw new Error("SQLCipher key is invalid");
      return existing;
    }
    const randomBytes = await dependencies.crypto.getRandomBytesAsync(32);
    if (!(randomBytes instanceof Uint8Array) || randomBytes.length !== 32) {
      throw new Error("Secure SQLCipher key generation failed");
    }
    const key = bytesToHex(randomBytes);
    await dependencies.secureStore.setItemAsync(SNAPSHOT_KEY_STORAGE_KEY, key);
    const verified = await dependencies.secureStore.getItemAsync(SNAPSHOT_KEY_STORAGE_KEY);
    if (verified !== key) throw new Error("SQLCipher key verification failed");
    return key;
  };

  const getDatabase = async (): Promise<SnapshotDatabase> => {
    if (databasePromise !== null) return databasePromise;
    keyPromise ??= getOrCreateKey();
    databasePromise = (async () => {
      const key = await keyPromise;
      const database = await dependencies.sqlite.openDatabaseAsync(SNAPSHOT_DATABASE_NAME);
      await database.execAsync(`PRAGMA key = "x'${key}'"`);
      await database.execAsync(
        "CREATE TABLE IF NOT EXISTS verified_snapshot (id INTEGER PRIMARY KEY CHECK (id = 1), value TEXT NOT NULL)",
      );
      return database;
    })();
    try {
      return await databasePromise;
    } catch (error) {
      databasePromise = null;
      throw error;
    }
  };

  const saveVerifiedSnapshot = async <T>(snapshot: VerifiedSnapshot<T>): Promise<void> => {
    assertSnapshot(snapshot);
    const serialized = JSON.stringify(snapshot);
    const database = await getDatabase();
    await database.runAsync(
      "INSERT INTO verified_snapshot (id, value) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET value = excluded.value",
      serialized,
    );
    const persisted = await database.getFirstAsync("SELECT value FROM verified_snapshot WHERE id = 1");
    if (persisted?.value !== serialized) throw new Error("Verified snapshot persistence failed");
  };

  const loadVerifiedSnapshot = async <T>(): Promise<VerifiedSnapshot<T> | null> => {
    const database = await getDatabase();
    const row = await database.getFirstAsync("SELECT value FROM verified_snapshot WHERE id = 1");
    if (row === null) return null;
    let snapshot: VerifiedSnapshot<T>;
    try {
      snapshot = JSON.parse(row.value) as VerifiedSnapshot<T>;
    } catch {
      throw new Error("Verified snapshot is invalid");
    }
    assertSnapshot(snapshot);
    return snapshot;
  };

  return { loadVerifiedSnapshot, saveVerifiedSnapshot };
}

const snapshotStorage = createSnapshotStorage();

export const loadVerifiedSnapshot = snapshotStorage.loadVerifiedSnapshot;
export const saveVerifiedSnapshot = snapshotStorage.saveVerifiedSnapshot;
