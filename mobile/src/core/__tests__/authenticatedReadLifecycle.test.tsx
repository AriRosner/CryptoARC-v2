import * as SecureStore from "expo-secure-store";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import React, { useEffect } from "react";

import { mobileQueryClient } from "../api/queryClient";
import { MobileApiError } from "../api/errors";
import { authenticatedRead } from "../api/authenticatedRead";
import {
  LEGACY_API_BASE_KEY,
  LEGACY_DEVICE_KEY,
  LEGACY_TOKEN_KEY,
  SESSION_CONTROL_KEY,
} from "../session/storage";
import {
  SessionProvider,
  type SessionContextValue,
  useSession,
} from "../session/SessionProvider";
import { fetchPortfolio } from "../../features/portfolio/api";
import { PortfolioScreen } from "../../features/portfolio/PortfolioScreen";
import type { PortfolioPayload } from "../../features/portfolio/types";
import { fetchPositionDetail } from "../../features/positions/api";
import { PositionDetailScreen } from "../../features/positions/PositionDetailScreen";
import type { PositionDetail } from "../../features/positions/types";
import type { MobileDevice } from "../../types";
import {
  clearVerifiedSnapshot,
  loadVerifiedSnapshot,
  saveVerifiedSnapshot,
} from "../storage/snapshot";

const mockRouterPush = jest.fn();

jest.mock("expo-router", () => ({
  router: {
    push: (...args: unknown[]) => mockRouterPush(...args),
  },
}));

jest.mock("../../features/portfolio/api", () => ({
  fetchPortfolio: jest.fn(),
}));

jest.mock("../../features/positions/api", () => ({
  fetchPositionDetail: jest.fn(),
}));

jest.mock("../storage/snapshot", () => ({
  clearVerifiedSnapshot: jest.fn(async () => undefined),
  createSnapshotBinding: jest.fn(async ({ deviceId }: { deviceId: string }) => ({
    ownerId: "a".repeat(64),
    deviceId,
    sessionId: "b".repeat(64),
  })),
  loadVerifiedSnapshot: jest.fn(async () => null),
  saveVerifiedSnapshot: jest.fn(async () => undefined),
}));

jest.mock("victory-native", () => {
  const ReactModule = jest.requireActual("react");
  const { View } = jest.requireActual("react-native");
  return {
    CartesianChart: ({
      children,
      data,
    }: {
      children(args: { points: { value: Array<{ x: number; y: number }> } }): React.ReactNode;
      data: Array<{ timestamp: number; value: number }>;
    }) => (
      <View>
        {children({
          points: {
            value: data.map((point) => ({ x: point.timestamp, y: point.value })),
          },
        })}
      </View>
    ),
    Line: () => null,
  };
});

jest.mock("@gorhom/bottom-sheet", () => {
  const ReactModule = jest.requireActual("react");
  const { View } = jest.requireActual("react-native");
  return {
    BottomSheetBackdrop: () => null,
    BottomSheetModal: ReactModule.forwardRef(
      ({ children }: { children?: React.ReactNode }, ref: React.ForwardedRef<unknown>) => {
        ReactModule.useImperativeHandle(ref, () => ({
          dismiss: jest.fn(),
          present: jest.fn(),
        }));
        return <View>{children}</View>;
      },
    ),
    BottomSheetScrollView: ({ children }: { children?: React.ReactNode }) => (
      <View>{children}</View>
    ),
  };
});

interface Deferred<T> {
  promise: Promise<T>;
  reject(error: Error): void;
  resolve(value: T): void;
}

function deferred<T>(): Deferred<T> {
  let reject!: (error: Error) => void;
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    reject = rejectPromise;
    resolve = resolvePromise;
  });
  return { promise, reject, resolve };
}

const deviceA: MobileDevice = {
  id: "device-a",
  name: "Device A",
  platform: "android",
  scopes: ["mobile:portfolio:read"],
  created_at: "2026-07-28T10:00:00.000Z",
  last_seen_at: "2026-07-28T10:00:00.000Z",
  expires_at: "2026-08-28T10:00:00.000Z",
  revoked_at: "",
};

const deviceB: MobileDevice = {
  ...deviceA,
  id: "device-b",
  name: "Device B",
};

function portfolioPayload(symbol: string, value: number): PortfolioPayload {
  return {
    artifact_type: "cryptoarc_mobile_portfolio",
    format_version: 1,
    generated_at: "2026-07-28T12:00:00.000Z",
    timeframe: "1d",
    freshness: {
      status: "fresh",
      generated_at: "2026-07-28T12:00:00.000Z",
      age_seconds: 1,
      stale_after_seconds: 30,
      approximate_pnl: true,
    },
    summary: {
      equity_sol: null,
      tracked_value_sol: value,
      cost_basis_sol: value / 2,
      net_pnl_sol: value / 2,
      realized_pnl_sol: value / 4,
      selected_period_realized_pnl_sol: value / 4,
      unrealized_pnl_sol: 0,
      win_rate_pct: 50,
      health_score: 90,
      open_positions: 1,
      closed_trades: 1,
    },
    current_snapshot: {
      generated_at: "2026-07-28T12:00:00.000Z",
      tracked_value_sol: value,
      cost_basis_sol: value / 2,
      realized_pnl_sol: 0,
      unrealized_pnl_sol: value / 2,
      net_pnl_sol: value / 2,
      paper_pnl_sol: value / 2,
      live_pnl_sol: 0,
      open_positions: 1,
      approximate: true,
    },
    series: [],
    allocation: [
      {
        key: `paper:${symbol}`,
        label: symbol,
        value_sol: value,
        percentage: 100,
        mode: "paper",
      },
    ],
    positions: [
      {
        id: `paper:${symbol}`,
        mode: "paper",
        symbol,
        mint: `${symbol}-mint`,
        status: "open",
        opened_at: "2026-07-28T10:00:00.000Z",
        updated_at: "2026-07-28T12:00:00.000Z",
        cost_basis_sol: value / 2,
        value_sol: value,
        realized_pnl_sol: 0,
        unrealized_pnl_sol: value / 2,
        pnl_pct: 100,
        pnl_approximate: true,
        mark_fresh: true,
        mark_age_seconds: 1,
        mark_source: "test",
      },
    ],
  };
}

const detail: PositionDetail = {
  id: "paper:AAA",
  mode: "paper",
  symbol: "AAA",
  mint: "AAA-mint",
  status: "open",
  opened_at: "2026-07-28T10:00:00.000Z",
  updated_at: "2026-07-28T12:00:00.000Z",
  wallet_label: "",
  token_balance: 100,
  cost_basis_sol: 0.2,
  value_sol: 0.4,
  realized_pnl_sol: 0,
  unrealized_pnl_sol: 0.2,
  pnl_pct: 100,
  pnl_approximate: true,
  mark_fresh: true,
  mark_age_seconds: 1,
  mark_source: "test",
  mark: {
    price_sol: 0.004,
    source: "test",
    confidence: 1,
    observed_at: "2026-07-28T12:00:00.000Z",
    age_seconds: 1,
    fresh: true,
  },
  pnl: {
    realized_sol: 0,
    unrealized_sol: 0.2,
    total_sol: 0.2,
    percentage: 100,
    approximate: true,
    confidence: "estimated",
    notes: [],
  },
  reconciliation_status: "matched",
  version: 4,
  stop_pct: 20,
  target_pct: 40,
  prepared_close: null,
  allowed_actions: {
    adjust_exit: false,
    close: false,
    reason: "Review required.",
  },
};

function SessionProbe({
  onChange,
}: {
  onChange(value: SessionContextValue): void;
}) {
  const session = useSession();
  useEffect(() => {
    onChange(session);
  }, [onChange, session]);
  return null;
}

function TestStack({
  children,
  onSession,
}: {
  children: React.ReactNode;
  onSession(value: SessionContextValue): void;
}) {
  return (
    <QueryClientProvider client={mobileQueryClient}>
      <SessionProvider>
        <SessionProbe onChange={onSession} />
        {children}
      </SessionProvider>
    </QueryClientProvider>
  );
}

describe("authenticated mobile read lifecycle", () => {
  const fetchPortfolioMock = jest.mocked(fetchPortfolio);
  const fetchPositionDetailMock = jest.mocked(fetchPositionDetail);
  const secureValues = new Map<string, string>();
  const queryDefaults = mobileQueryClient.getDefaultOptions();

  beforeAll(() => {
    mobileQueryClient.setDefaultOptions({
      ...queryDefaults,
      queries: {
        ...queryDefaults.queries,
        gcTime: Infinity,
      },
    });
  });

  afterAll(() => {
    mobileQueryClient.setDefaultOptions(queryDefaults);
    mobileQueryClient.clear();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mobileQueryClient.clear();
    secureValues.clear();
    secureValues.set(LEGACY_API_BASE_KEY, "https://device-a.test");
    secureValues.set(LEGACY_TOKEN_KEY, "token-a");
    secureValues.set(LEGACY_DEVICE_KEY, JSON.stringify(deviceA));
    jest.mocked(loadVerifiedSnapshot).mockResolvedValue(null);
    jest.mocked(SecureStore.getItemAsync).mockImplementation(
      async (key) => secureValues.get(key) ?? null,
    );
    jest.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value) => {
      secureValues.set(key, value);
    });
    jest.mocked(SecureStore.deleteItemAsync).mockImplementation(async (key) => {
      secureValues.delete(key);
    });
  });

  afterEach(async () => {
    await act(async () => {
      mobileQueryClient.clear();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  });

  async function waitForQuarantinePersistence() {
    await waitFor(() =>
      expect(secureValues.get(SESSION_CONTROL_KEY)).toContain(
        '"status":"cleared"',
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  it("quarantines generation A data and never exposes it to replacement B", async () => {
    const payloadB = deferred<PortfolioPayload>();
    const revokedRead = deferred<PortfolioPayload>();
    fetchPortfolioMock.mockImplementation(async (timeframe, options) => {
      if (options?.token === "token-a" && timeframe === "1d") {
        return portfolioPayload("AAA", 0.42);
      }
      if (options?.token === "token-a") {
        return revokedRead.promise;
      }
      if (options?.token === "token-b") return payloadB.promise;
      throw new Error("unauthenticated request dispatched");
    });
    let session!: SessionContextValue;
    const view = await render(
      <TestStack onSession={(value) => (session = value)}>
        <PortfolioScreen />
      </TestStack>,
    );
    await waitFor(() => expect(session.token).toBe("token-a"));
    expect((await view.findAllByText("AAA")).length).toBeGreaterThan(0);
    const generationA = session.generation;

    fireEvent.press(view.getByText("1W"));
    await waitFor(() => expect(fetchPortfolioMock).toHaveBeenCalledTimes(2));
    await act(async () => {
      revokedRead.reject(
        new MobileApiError("session revoked", "authentication", 401, false),
      );
      await Promise.resolve();
      await Promise.resolve();
    });
    await waitFor(() => expect(session.token).toBeNull());
    await waitForQuarantinePersistence();

    expect(view.queryAllByText("AAA")).toHaveLength(0);
    expect((await view.findAllByText("Go to Pairing")).length).toBeGreaterThan(0);
    expect(
      mobileQueryClient
        .getQueryCache()
        .findAll({ queryKey: ["mobile"] })
        .some((query) => query.queryKey.includes(generationA)),
    ).toBe(false);
    const callsAfterQuarantine = fetchPortfolioMock.mock.calls.length;
    fireEvent.press(view.getAllByText("Go to Pairing")[0]);
    expect(mockRouterPush).toHaveBeenCalledWith("/pairing");
    expect(fetchPortfolioMock).toHaveBeenCalledTimes(callsAfterQuarantine);

    await session.replaceSession(
      "https://device-b.test",
      "token-b",
      deviceB,
      session.generation,
    );
    await waitFor(() => expect(session.token).toBe("token-b"));
    expect(view.queryAllByText("AAA")).toHaveLength(0);
    await act(async () => {
      payloadB.resolve(portfolioPayload("BBB", 0.84));
      await Promise.resolve();
    });
    expect((await view.findAllByText("BBB")).length).toBeGreaterThan(0);
    await view.unmount();
  });

  it("ignores a late generation A 401 after replacement B is active", async () => {
    const payloadA = deferred<PortfolioPayload>();
    fetchPortfolioMock.mockImplementation(async (_timeframe, options) => {
      if (options?.token === "token-a") return payloadA.promise;
      if (options?.token === "token-b") return portfolioPayload("BBB", 0.84);
      throw new Error("unauthenticated request dispatched");
    });
    let session!: SessionContextValue;
    const view = await render(
      <TestStack onSession={(value) => (session = value)}>
        <PortfolioScreen />
      </TestStack>,
    );
    await waitFor(() => expect(session.token).toBe("token-a"));
    await waitFor(() =>
      expect(fetchPortfolioMock).toHaveBeenCalledWith("1d", {
        apiBaseUrl: "https://device-a.test",
        token: "token-a",
      }),
    );

    await act(async () => {
      await session.replaceSession(
        "https://device-b.test",
        "token-b",
        deviceB,
        session.generation,
      );
    });
    expect((await view.findAllByText("BBB")).length).toBeGreaterThan(0);
    await act(async () => {
      payloadA.reject(new MobileApiError("old session revoked", "authentication", 401, false));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(session.token).toBe("token-b");
    expect(view.getAllByText("BBB").length).toBeGreaterThan(0);
    await view.unmount();
  });

  it("shows a 403 denial without cached detail or session quarantine", async () => {
    fetchPositionDetailMock
      .mockResolvedValueOnce(detail)
      .mockRejectedValueOnce(
        new MobileApiError("scope denied", "authorization", 403, false),
      );
    let session!: SessionContextValue;
    const view = await render(
      <TestStack onSession={(value) => (session = value)}>
        <PositionDetailScreen positionId="paper:AAA" onBack={jest.fn()} />
      </TestStack>,
    );
    await waitFor(() => expect(session?.token).toBe("token-a"));
    expect((await view.findAllByText("AAA")).length).toBeGreaterThan(0);

    await act(async () => {
      await mobileQueryClient.invalidateQueries({
        queryKey: ["mobile", "position", "paper:AAA"],
      });
    });

    expect(await view.findByText("This device does not have positions access.")).toBeTruthy();
    expect(view.queryByText("AAA")).toBeNull();
    expect(session.token).toBe("token-a");
    expect(view.queryByText("Go to Pairing")).toBeNull();
    await view.unmount();
  });

  it("never dispatches a manual refetch without an authenticated token", async () => {
    const operation = jest.fn(async () => detail);
    const revokeSession = jest.fn(async () => true);

    await expect(
      authenticatedRead(
        { generation: 8, token: null, revokeSession },
        operation,
      ),
    ).rejects.toMatchObject({ status: 401 });

    expect(operation).not.toHaveBeenCalled();
    expect(revokeSession).not.toHaveBeenCalled();
  });

  it("persists a verified production portfolio read after authenticated success", async () => {
    fetchPortfolioMock.mockResolvedValue(portfolioPayload("AAA", 0.42));
    let session!: SessionContextValue;
    const view = await render(
      <TestStack onSession={(value) => (session = value)}>
        <PortfolioScreen />
      </TestStack>,
    );

    expect((await view.findAllByText("AAA")).length).toBeGreaterThan(0);
    await waitFor(() => expect(saveVerifiedSnapshot).toHaveBeenCalledTimes(1));
    expect(jest.mocked(saveVerifiedSnapshot).mock.calls[0][0]).toMatchObject({
      schemaVersion: 1,
      deviceId: "device-a",
      payload: {
        kind: "portfolio",
        data: { totalValueSol: 0.42 },
      },
    });
    expect(session.token).toBe("token-a");
    await view.unmount();
  });

  it("loads only an explicitly stale read-only snapshot after restart and replaces it with fresh data", async () => {
    jest.mocked(loadVerifiedSnapshot).mockResolvedValue({
      schemaVersion: 1,
      ownerId: "a".repeat(64),
      deviceId: "device-a",
      sessionId: "b".repeat(64),
      verifiedAt: "2026-07-28T12:00:00.000Z",
      serverTime: "2026-07-28T12:00:00.000Z",
      sequence: 0,
      payload: {
        kind: "portfolio",
        version: 1,
        data: {
          totalValueSol: 0.42,
          assets: [{
            assetIdentifier: { kind: "public_asset", chain: "solana", value: "paper:AAA" },
            assetMetadata: { symbol: "AAA" },
            balance: 0,
            valueSol: 0.42,
          }],
        },
      },
    });
    fetchPortfolioMock.mockRejectedValueOnce(new Error("offline"));
    let session!: SessionContextValue;
    const offline = await render(
      <TestStack onSession={(value) => (session = value)}>
        <PortfolioScreen />
      </TestStack>,
    );
    expect(await offline.findByText("Stale offline snapshot")).toBeTruthy();
    expect(offline.getByText("Read-only")).toBeTruthy();
    expect(offline.queryByText("Adjust exits")).toBeNull();
    await offline.unmount();

    mobileQueryClient.clear();
    fetchPortfolioMock.mockResolvedValueOnce(portfolioPayload("BBB", 0.84));
    const fresh = await render(
      <TestStack onSession={() => undefined}>
        <PortfolioScreen />
      </TestStack>,
    );
    expect((await fresh.findAllByText("BBB")).length).toBeGreaterThan(0);
    expect(fresh.queryByText("Stale offline snapshot")).toBeNull();
    await waitFor(() => expect(saveVerifiedSnapshot).toHaveBeenCalled());
    await fresh.unmount();
  });

  it("invalidates the encrypted snapshot on revocation", async () => {
    fetchPortfolioMock.mockRejectedValue(
      new MobileApiError("revoked", "authentication", 401, false),
    );
    let session!: SessionContextValue;
    const view = await render(
      <TestStack onSession={(value) => (session = value)}>
        <PortfolioScreen />
      </TestStack>,
    );
    await waitFor(() => expect(session.token).toBeNull());
    await waitFor(() => expect(clearVerifiedSnapshot).toHaveBeenCalled());
    expect(view.queryByText("Stale offline snapshot")).toBeNull();
    await view.unmount();
  });
});
