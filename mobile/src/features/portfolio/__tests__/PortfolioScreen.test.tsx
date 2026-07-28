import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import React from "react";

import { fetchPortfolio } from "../api";
import { PortfolioScreen } from "../PortfolioScreen";
import type { PortfolioPayload } from "../types";

jest.mock("../api", () => ({
  fetchPortfolio: jest.fn(),
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
    unrealized_pnl_sol: 0.07,
    win_rate_pct: 67,
    health_score: 91,
    open_positions: 1,
    closed_trades: 3,
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

describe("PortfolioScreen", () => {
  const fetchPortfolioMock = jest.mocked(fetchPortfolio);

  beforeEach(() => {
    jest.clearAllMocks();
    fetchPortfolioMock.mockImplementation(async (timeframe) => ({ ...payload, timeframe }));
  });

  it("shows portfolio metrics and switches the timeframe", async () => {
    const { client, view } = await renderPortfolio();

    expect(await view.findByText("Tracked value")).toBeTruthy();
    expect(view.getByText("Net performance")).toBeTruthy();
    expect(view.getByText("Win rate")).toBeTruthy();
    expect(view.getByText("Health")).toBeTruthy();

    await act(async () => {
      fireEvent.press(view.getByText("1W"));
      await Promise.resolve();
    });
    await waitFor(() => expect(fetchPortfolioMock).toHaveBeenLastCalledWith("1w"));
    await act(async () => {
      client.clear();
    });
  });
});
