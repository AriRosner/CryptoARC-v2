import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import * as SQLite from "expo-sqlite";

export interface PublicAssetIdentifier {
  kind: "public_asset";
  chain: string;
  value: string;
}

export interface PublicAssetMetadata {
  symbol: string;
  name?: string;
  imageUrl?: string;
}

export interface PortfolioAssetReadModel {
  assetIdentifier: PublicAssetIdentifier;
  assetMetadata?: PublicAssetMetadata;
  balance: number;
  valueSol?: number | null;
}

export type SnapshotReadModel =
  | {
      kind: "cockpit";
      version: 1;
      data: {
        botStatus: string;
        mode: string;
        nextOperatorAction: string;
        killSwitchEnabled: boolean;
      };
    }
  | {
      kind: "portfolio";
      version: 1;
      data: {
        totalValueSol: number;
        assets: PortfolioAssetReadModel[];
      };
    }
  | {
      kind: "positions";
      version: 1;
      data: {
        items: Array<{
          id: string;
          assetIdentifier: PublicAssetIdentifier;
          quantity: number;
          valueSol: number | null;
        }>;
      };
    }
  | {
      kind: "trades";
      version: 1;
      data: {
        items: Array<{
          id: string;
          assetIdentifier: PublicAssetIdentifier;
          side: string;
          status: string;
          amount: number;
          valueSol: number | null;
          createdAt: string;
        }>;
      };
    }
  | {
      kind: "wallet";
      version: 1;
      data: {
        addressLabel: string;
        balances: PortfolioAssetReadModel[];
      };
    }
  | {
      kind: "alerts";
      version: 1;
      data: {
        items: Array<{ id: string; level: string; message: string; createdAt: string }>;
      };
    }
  | {
      kind: "feed";
      version: 1;
      data: {
        generatedAt: string;
        items: Array<{ id: string; level: string; message: string; createdAt: string }>;
      };
    };

export interface VerifiedSnapshot {
  schemaVersion: 1;
  verifiedAt: string;
  serverTime: string;
  sequence: number;
  payload: SnapshotReadModel;
}

const SNAPSHOT_KEY_STORAGE_KEY = "cryptoarc.mobile.snapshot.sqlcipher-key.v1";
const SNAPSHOT_DATABASE_NAME = "cryptoarc-mobile-snapshot.db";

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

function readModelError(): never {
  throw new Error("Snapshot read model is invalid");
}

function assertPlainJsonValue(value: unknown, seen = new Set<object>()): void {
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  ) {
    return;
  }
  if (!value || typeof value !== "object" || seen.has(value)) return readModelError();
  seen.add(value);
  try {
    if (Array.isArray(value)) {
      if (Object.getPrototypeOf(value) !== Array.prototype) return readModelError();
      const descriptors = Object.getOwnPropertyDescriptors(value);
      const expectedKeys = new Set(["length"]);
      for (let index = 0; index < value.length; index += 1) {
        expectedKeys.add(String(index));
      }
      if (Reflect.ownKeys(descriptors).some((key) => typeof key !== "string" || !expectedKeys.has(key))) {
        return readModelError();
      }
      for (let index = 0; index < value.length; index += 1) {
        const descriptor = descriptors[String(index)];
        if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) return readModelError();
        assertPlainJsonValue(descriptor.value, seen);
      }
      return;
    }
    if (Object.getPrototypeOf(value) !== Object.prototype) return readModelError();
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== "string") return readModelError();
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (!descriptor?.enumerable || !("value" in descriptor)) return readModelError();
      assertPlainJsonValue(descriptor.value, seen);
    }
  } finally {
    seen.delete(value);
  }
}

function plainObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return readModelError();
  return value as Record<string, unknown>;
}

function exactKeys(
  value: Record<string, unknown>,
  required: readonly string[],
  optional: readonly string[] = [],
): void {
  const allowed = new Set([...required, ...optional]);
  if (
    required.some((key) => !(key in value)) ||
    Object.keys(value).some((key) => !allowed.has(key))
  ) {
    readModelError();
  }
}

function finiteNumber(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return readModelError();
  return value;
}

function stringValue(value: unknown): string {
  if (typeof value !== "string") return readModelError();
  return value;
}

function assertPublicAssetIdentifier(value: unknown): void {
  const identifier = plainObject(value);
  exactKeys(identifier, ["kind", "chain", "value"]);
  if (identifier.kind !== "public_asset") readModelError();
  if (!stringValue(identifier.chain) || !stringValue(identifier.value)) readModelError();
}

function assertPublicAssetMetadata(value: unknown): void {
  const metadata = plainObject(value);
  exactKeys(metadata, ["symbol"], ["name", "imageUrl"]);
  stringValue(metadata.symbol);
  if (metadata.name !== undefined) stringValue(metadata.name);
  if (metadata.imageUrl !== undefined) stringValue(metadata.imageUrl);
}

function assertAsset(value: unknown): void {
  const asset = plainObject(value);
  exactKeys(asset, ["assetIdentifier", "balance"], ["assetMetadata", "valueSol"]);
  assertPublicAssetIdentifier(asset.assetIdentifier);
  finiteNumber(asset.balance);
  if (asset.assetMetadata !== undefined) assertPublicAssetMetadata(asset.assetMetadata);
  if (asset.valueSol !== undefined && asset.valueSol !== null) finiteNumber(asset.valueSol);
}

function assertEventItem(value: unknown): void {
  const item = plainObject(value);
  exactKeys(item, ["id", "level", "message", "createdAt"]);
  stringValue(item.id);
  stringValue(item.level);
  stringValue(item.message);
  if (!Number.isFinite(Date.parse(stringValue(item.createdAt)))) readModelError();
}

function assertReadModel(value: unknown): asserts value is SnapshotReadModel {
  const model = plainObject(value);
  exactKeys(model, ["kind", "version", "data"]);
  if (model.version !== 1) readModelError();
  const data = plainObject(model.data);

  switch (model.kind) {
    case "cockpit":
      exactKeys(data, ["botStatus", "mode", "nextOperatorAction", "killSwitchEnabled"]);
      stringValue(data.botStatus);
      stringValue(data.mode);
      stringValue(data.nextOperatorAction);
      if (typeof data.killSwitchEnabled !== "boolean") readModelError();
      return;
    case "portfolio":
      exactKeys(data, ["totalValueSol", "assets"]);
      finiteNumber(data.totalValueSol);
      if (!Array.isArray(data.assets)) readModelError();
      data.assets.forEach(assertAsset);
      return;
    case "positions":
      exactKeys(data, ["items"]);
      if (!Array.isArray(data.items)) readModelError();
      data.items.forEach((value) => {
        const item = plainObject(value);
        exactKeys(item, ["id", "assetIdentifier", "quantity", "valueSol"]);
        stringValue(item.id);
        assertPublicAssetIdentifier(item.assetIdentifier);
        finiteNumber(item.quantity);
        if (item.valueSol !== null) finiteNumber(item.valueSol);
      });
      return;
    case "trades":
      exactKeys(data, ["items"]);
      if (!Array.isArray(data.items)) readModelError();
      data.items.forEach((value) => {
        const item = plainObject(value);
        exactKeys(item, [
          "id",
          "assetIdentifier",
          "side",
          "status",
          "amount",
          "valueSol",
          "createdAt",
        ]);
        stringValue(item.id);
        assertPublicAssetIdentifier(item.assetIdentifier);
        stringValue(item.side);
        stringValue(item.status);
        finiteNumber(item.amount);
        if (item.valueSol !== null) finiteNumber(item.valueSol);
        if (!Number.isFinite(Date.parse(stringValue(item.createdAt)))) readModelError();
      });
      return;
    case "wallet":
      exactKeys(data, ["addressLabel", "balances"]);
      stringValue(data.addressLabel);
      if (!Array.isArray(data.balances)) readModelError();
      data.balances.forEach(assertAsset);
      return;
    case "alerts":
      exactKeys(data, ["items"]);
      if (!Array.isArray(data.items)) readModelError();
      data.items.forEach(assertEventItem);
      return;
    case "feed":
      exactKeys(data, ["generatedAt", "items"]);
      if (!Number.isFinite(Date.parse(stringValue(data.generatedAt)))) readModelError();
      if (!Array.isArray(data.items)) readModelError();
      data.items.forEach(assertEventItem);
      return;
    default:
      readModelError();
  }
}

function assertSnapshot(snapshot: VerifiedSnapshot): void {
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

  const saveVerifiedSnapshot = async (snapshot: VerifiedSnapshot): Promise<void> => {
    assertPlainJsonValue(snapshot);
    const serialized = JSON.stringify(snapshot);
    let serializedSnapshot: VerifiedSnapshot;
    try {
      serializedSnapshot = JSON.parse(serialized) as VerifiedSnapshot;
    } catch {
      throw new Error("Snapshot read model is invalid");
    }
    assertSnapshot(serializedSnapshot);
    const database = await getDatabase();
    await database.runAsync(
      "INSERT INTO verified_snapshot (id, value) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET value = excluded.value",
      serialized,
    );
    const persisted = await database.getFirstAsync("SELECT value FROM verified_snapshot WHERE id = 1");
    if (persisted?.value !== serialized) throw new Error("Verified snapshot persistence failed");
  };

  const loadVerifiedSnapshot = async (): Promise<VerifiedSnapshot | null> => {
    const database = await getDatabase();
    const row = await database.getFirstAsync("SELECT value FROM verified_snapshot WHERE id = 1");
    if (row === null) return null;
    let snapshot: VerifiedSnapshot;
    try {
      snapshot = JSON.parse(row.value) as VerifiedSnapshot;
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
