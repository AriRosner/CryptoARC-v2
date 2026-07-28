import { createSnapshotStorage } from "../storage/snapshot";
import type {
  SnapshotReadModel,
  VerifiedSnapshot,
} from "../storage/snapshot";

interface FakeRow {
  value: string;
}

function snapshotFixture() {
  const calls: string[] = [];
  let row: FakeRow | null = null;
  const database = {
    execAsync: jest.fn(async (sql: string) => {
      calls.push(`exec:${sql}`);
    }),
    getFirstAsync: jest.fn(async (_sql: string, ..._params: unknown[]) => {
      calls.push("get");
      return row;
    }),
    runAsync: jest.fn(async (_sql: string, value: string) => {
      calls.push("run");
      row = { value };
      return { changes: 1, lastInsertRowId: 1 };
    }),
  };
  const secureValues = new Map<string, string>();
  const secureStore = {
    getItemAsync: jest.fn(async (key: string) => {
      calls.push(`secure-get:${key}`);
      return secureValues.get(key) ?? null;
    }),
    setItemAsync: jest.fn(async (key: string, value: string) => {
      calls.push(`secure-set:${key}`);
      secureValues.set(key, value);
    }),
  };
  const crypto = {
    getRandomBytesAsync: jest.fn(async () => Uint8Array.from({ length: 32 }, (_value, index) => index)),
  };
  const sqlite = {
    openDatabaseAsync: jest.fn(async () => {
      calls.push("open");
      return database;
    }),
  };

  return { calls, crypto, database, secureStore, secureValues, sqlite };
}

const verifiedSnapshot: VerifiedSnapshot = {
  schemaVersion: 1,
  verifiedAt: "2026-07-28T12:00:00.000Z",
  serverTime: "2026-07-28T12:00:00.000Z",
  sequence: 42,
  payload: {
    kind: "portfolio",
    version: 1,
    data: {
      totalValueSol: 12.5,
      assets: [],
    },
  },
};

describe("SQLCipher verified snapshots", () => {
  it("generates one secure random key and applies PRAGMA key before schema or data access", async () => {
    const fixture = snapshotFixture();
    const storage = createSnapshotStorage({
      crypto: fixture.crypto,
      secureStore: fixture.secureStore,
      sqlite: fixture.sqlite,
    });

    await storage.saveVerifiedSnapshot(verifiedSnapshot);
    await storage.loadVerifiedSnapshot();

    expect(fixture.crypto.getRandomBytesAsync).toHaveBeenCalledTimes(1);
    const storedKeys = [...fixture.secureValues.values()];
    expect(storedKeys).toHaveLength(1);
    expect(storedKeys[0]).toMatch(/^[a-f0-9]{64}$/);

    const openIndex = fixture.calls.indexOf("open");
    const pragmaIndex = fixture.calls.findIndex((call) => call.startsWith("exec:PRAGMA key"));
    const schemaIndex = fixture.calls.findIndex((call) => call.startsWith("exec:CREATE TABLE"));
    const dataIndex = fixture.calls.indexOf("run");
    expect(pragmaIndex).toBe(openIndex + 1);
    expect(schemaIndex).toBeGreaterThan(pragmaIndex);
    expect(dataIndex).toBeGreaterThan(schemaIndex);
  });

  it("round-trips only a valid verified read model", async () => {
    const fixture = snapshotFixture();
    const storage = createSnapshotStorage({
      crypto: fixture.crypto,
      secureStore: fixture.secureStore,
      sqlite: fixture.sqlite,
    });

    await storage.saveVerifiedSnapshot(verifiedSnapshot);

    await expect(storage.loadVerifiedSnapshot()).resolves.toEqual(verifiedSnapshot);
  });

  it("rejects secret-bearing or non-read-model payloads", async () => {
    const fixture = snapshotFixture();
    const storage = createSnapshotStorage({
      crypto: fixture.crypto,
      secureStore: fixture.secureStore,
      sqlite: fixture.sqlite,
    });

    await expect(
      storage.saveVerifiedSnapshot({
        ...verifiedSnapshot,
        payload: {
          kind: "portfolio",
          version: 1,
          data: { totalValueSol: 12.5, assets: [], access_token: "must-not-persist" },
        } as unknown as SnapshotReadModel,
      }),
    ).rejects.toThrow("Snapshot read model is invalid");
    expect(fixture.database.runAsync).not.toHaveBeenCalled();
  });

  it.each([
    { actions: [] },
    { command: "stop" },
    { queue: [] },
    { idempotencyKey: "action-1" },
    { token: "ambiguous-session-or-asset-token" },
    { credential: "secret" },
  ])("rejects non-allowlisted action or credential material: %j", async (extra) => {
    const fixture = snapshotFixture();
    const storage = createSnapshotStorage({
      crypto: fixture.crypto,
      secureStore: fixture.secureStore,
      sqlite: fixture.sqlite,
    });

    await expect(
      storage.saveVerifiedSnapshot({
        ...verifiedSnapshot,
        payload: {
          kind: "portfolio",
          version: 1,
          data: { totalValueSol: 12.5, assets: [], ...extra },
        },
      }),
    ).rejects.toThrow("Snapshot read model is invalid");
    expect(fixture.database.runAsync).not.toHaveBeenCalled();
  });

  it("allows explicitly typed public asset identifiers and metadata", async () => {
    const fixture = snapshotFixture();
    const storage = createSnapshotStorage({
      crypto: fixture.crypto,
      secureStore: fixture.secureStore,
      sqlite: fixture.sqlite,
    });

    await expect(
      storage.saveVerifiedSnapshot({
        ...verifiedSnapshot,
        payload: {
          kind: "portfolio",
          version: 1,
          data: {
            totalValueSol: 12.5,
            assets: [
              {
                assetIdentifier: {
                  kind: "public_asset",
                  chain: "solana",
                  value: "So11111111111111111111111111111111111111112",
                },
                assetMetadata: { symbol: "SOL", name: "Wrapped SOL" },
                balance: 12.5,
                valueSol: 12.5,
              },
            ],
          },
        },
      }),
    ).resolves.toBeUndefined();
  });

  it("fails closed when the persisted SQLCipher key is malformed", async () => {
    const fixture = snapshotFixture();
    fixture.secureValues.set("cryptoarc.mobile.snapshot.sqlcipher-key.v1", "not-a-key");
    const storage = createSnapshotStorage({
      crypto: fixture.crypto,
      secureStore: fixture.secureStore,
      sqlite: fixture.sqlite,
    });

    await expect(storage.loadVerifiedSnapshot()).rejects.toThrow("SQLCipher key is invalid");
    expect(fixture.crypto.getRandomBytesAsync).not.toHaveBeenCalled();
    expect(fixture.sqlite.openDatabaseAsync).not.toHaveBeenCalled();
  });
});
