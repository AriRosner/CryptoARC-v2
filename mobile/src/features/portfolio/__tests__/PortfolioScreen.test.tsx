import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import React from "react";

import { fetchPortfolio } from "../api";
import { PortfolioScreen } from "../PortfolioScreen";
import type { PortfolioPayload } from "../types";
import { MobileApiError } from "../../../core/api/errors";

jest.mock("../api", () => ({
  fetchPortfolio: jest.fn(),
}));

const mockRevokeSession = jest.fn(async () => undefined);

jest.mock("../../../core/session/SessionProvider", () => ({
  useOptionalSession: () => ({
    apiBaseUrl: "https://cryptoarc.test",
    token: "mobile-token",
    generation: 3,
    revokeSession: mockRevokeSession,
  }),
}));

jest.mock("victory-native", () => {
  const ReactModule = jest.requireActual("react");
  const { View: MockView } = jest.requireActual("react-native");
  return {
    CartesianChart: ({
      children,
    }: {
      children(args: { points: { value: [] } }): React.ReactNode;
    }) => <MockView>{children({ points: { value: [] } })}</MockView>,
    Line: () => null,
  };
});

const payload: PortfolioPayload = {
  artifact_type: "cryptoarc_mobile_portfolio",
  format_version: 1,
  generated_at: "2026-07-28T12:00:00.000Z",
  timeframe: "1d",
  freshness: {
    status: "fresh",
    generated_at: "2026-07-28T12:00:00.000Z",
    age_seconds: 4,
    stale_after_seconds: 30,
    approximate_pnl: true,
  },
  summary: {
    equity_sol: null,
    tracked_value_sol: 0.42,
    cost_basis_sol: 0.2,
    net_pnl_sol: 0.22,
    realized_pnl_sol: 0.15,
    selected_period_realized_pnl_sol: 0.15,
    unrealized_pnl_sol: 0.07,
    win_rate_pct: 67,
    health_score: 91,
    open_positions: 1,
    closed_trades: 3,
  },
  current_snapshot: {
    generated_at: "2026-07-28T12:00:00.000Z",
    tracked_value_sol: 0.42,
    cost_basis_sol: 0.2,
    realized_pnl_sol: 0.15,
    unrealized_pnl_sol: 0.07,
    net_pnl_sol: 0.22,
    paper_pnl_sol: 0.15,
    live_pnl_sol: 0.07,
    open_positions: 1,
    approximate: true,
  },
  series: [
    {
      at: "2026-07-28T11:00:00.000Z",
      net_pnl_sol: 0.15,
      paper_pnl_sol: 0.15,
      live_pnl_sol: 0,
      current_snapshot: false,
      approximate: false,
    },
    {
      at: "2026-07-28T12:00:00.000Z",
      net_pnl_sol: 0.22,
      paper_pnl_sol: 0.15,
      live_pnl_sol: 0.07,
      current_snapshot: true,
      approximate: true,
    },
  ],
  allocation: [
    { key: "paper:token-1", label: "ARC", value_sol: 0.42, percentage: 100, mode: "paper" },
  ],
  positions: [
    {
      id: "paper:token-1",
      mode: "paper",
      symbol: "ARC",
      mint: "mint-1",
      status: "open",
      opened_at: "2026-07-28T11:00:00.000Z",
      updated_at: "2026-07-28T12:00:00.000Z",
      cost_basis_sol: 0.2,
      value_sol: 0.42,
      realized_pnl_sol: 0,
      unrealized_pnl_sol: 0.22,
      pnl_pct: 110,
      pnl_approximate: true,
      mark_fresh: true,
      mark_age_seconds: 4,
      mark_source: "pumpportal",
    },
  ],
};

async function renderPortfolio() {
  const client = new QueryClient({
    defaultOptions: { queries: { gcTime: 0, retry: false } },
  });
  const view = await render(
    <QueryClientProvider client={client}>
      <PortfolioScreen />
    </QueryClientProvider>,
  );
  return { client, view };
}

async function cleanupPortfolio(
  client: QueryClient,
  view: Awaited<ReturnType<typeof render>>,
) {
  await act(async () => {
    view.unmount();
    client.clear();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("PortfolioScreen", () => {
  const fetchPortfolioMock = jest.mocked(fetchPortfolio);

  beforeEach(() => {
    jest.clearAllMocks();
    fetchPortfolioMock.mockImplementation(async (timeframe) => ({ ...payload, timeframe }));
  });

  it("shows portfolio metrics and switches the timeframe", async () => {
    const { client, view } = await renderPortfolio();

    expect(await view.findByText("Current tracked value")).toBeTruthy();
    expect(view.getByText("Period realized")).toBeTruthy();
    expect(view.getByText("Win rate")).toBeTruthy();
    expect(view.getByText("Health")).toBeTruthy();

    await act(async () => {
      fireEvent.press(view.getByText("1W"));
      await Promise.resolve();
    });
    await waitFor(() =>
      expect(fetchPortfolioMock).toHaveBeenLastCalledWith("1w", {
        apiBaseUrl: "https://cryptoarc.test",
        token: "mobile-token",
      }),
    );
    await cleanupPortfolio(client, view);
  });

  it("quarantines a revoked session after a portfolio 401", async () => {
    fetchPortfolioMock.mockRejectedValueOnce(
      new MobileApiError("session revoked", "authentication", 401, false),
    );
    const { client, view } = await renderPortfolio();

    await waitFor(() => expect(mockRevokeSession).toHaveBeenCalledTimes(1));
    expect(await view.findByText("Pair this device again to view Portfolio.")).toBeTruthy();
    await cleanupPortfolio(client, view);
  });

  it("keeps a valid session mounted after a portfolio scope denial", async () => {
    fetchPortfolioMock.mockRejectedValueOnce(
      new MobileApiError("portfolio scope required", "authorization", 403, false),
    );
    const { client, view } = await renderPortfolio();

    expect(await view.findByText("This device does not have Portfolio access.")).toBeTruthy();
    expect(mockRevokeSession).not.toHaveBeenCalled();
    await cleanupPortfolio(client, view);
  });

  it("labels preserved 1D data when the selected 1W request fails", async () => {
    fetchPortfolioMock
      .mockResolvedValueOnce(payload)
      .mockRejectedValueOnce(new MobileApiError("offline", "connection", null, true));
    const { client, view } = await renderPortfolio();
    expect(await view.findByText("Current tracked value")).toBeTruthy();

    await act(async () => {
      fireEvent.press(view.getByText("1W"));
      await Promise.resolve();
    });

    expect(await view.findByText("Showing cached 1D data; 1W is unavailable.")).toBeTruthy();
    await cleanupPortfolio(client, view);
  });

  it("matches all four loaded metric tiles in the initial skeleton", async () => {
    fetchPortfolioMock.mockReturnValue(new Promise(() => undefined));
    const { client, view } = await renderPortfolio();

    expect(view.getAllByTestId("portfolio-metric-skeleton")).toHaveLength(4);
    await cleanupPortfolio(client, view);
  });
});
