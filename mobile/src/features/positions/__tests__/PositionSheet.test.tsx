import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { fetchPositionDetail } from "../api";
import { PositionSheet } from "../PositionSheet";
import type { PositionDetail } from "../types";

jest.mock("@gorhom/bottom-sheet", () => {
  const ReactModule = jest.requireActual("react");
  const { View: MockView } = jest.requireActual("react-native");
  return {
    BottomSheetBackdrop: () => null,
    BottomSheetModal: ReactModule.forwardRef(
      ({ children }: { children?: React.ReactNode }, _ref: React.ForwardedRef<unknown>) => (
        <MockView>{children}</MockView>
      ),
    ),
    BottomSheetView: ({ children }: { children?: React.ReactNode }) => <MockView>{children}</MockView>,
  };
});

jest.mock("../api", () => ({
  fetchPositionDetail: jest.fn(),
}));

const detail: PositionDetail = {
  id: "live-position-1",
  mode: "live",
  symbol: "ARC",
  mint: "mint-live",
  status: "open",
  opened_at: "2026-07-28T11:00:00.000Z",
  updated_at: "2026-07-28T12:00:00.000Z",
  wallet_label: "wallet...blic",
  token_balance: 1000,
  cost_basis_sol: 0.2,
  value_sol: 0.28,
  realized_pnl_sol: 0,
  unrealized_pnl_sol: 0.08,
  pnl_pct: 40,
  pnl_approximate: true,
  mark_fresh: true,
  mark_age_seconds: 4,
  mark_source: "pumpportal:direct",
  mark: {
    price_sol: 0.00028,
    source: "pumpportal:direct",
    confidence: 0.93,
    observed_at: "2026-07-28T11:59:56.000Z",
    age_seconds: 4,
    fresh: true,
  },
  pnl: {
    realized_sol: 0,
    unrealized_sol: 0.08,
    total_sol: 0.08,
    percentage: 40,
    approximate: true,
    confidence: "estimated",
    notes: ["Live PnL remains approximate until reconciliation."],
  },
  reconciliation_status: "matched",
  allowed_actions: {
    adjust_exit: false,
    close: false,
    reason: "Guarded position actions are available in the review flow.",
  },
};

describe("PositionSheet", () => {
  const fetchPositionDetailMock = jest.mocked(fetchPositionDetail);

  beforeEach(() => {
    jest.clearAllMocks();
    fetchPositionDetailMock.mockResolvedValue(detail);
  });

  it("shows summary fields, guarded actions, and opens full details", async () => {
    const onOpenDetails = jest.fn();
    const onAdjustExit = jest.fn();
    const onClose = jest.fn();
    const client = new QueryClient({ defaultOptions: { queries: { gcTime: 0, retry: false } } });

    const view = await render(
      <QueryClientProvider client={client}>
        <PositionSheet
          positionId="live-position-1"
          onDismiss={jest.fn()}
          onOpenDetails={onOpenDetails}
          onAdjustExit={onAdjustExit}
          onClose={onClose}
        />
      </QueryClientProvider>,
    );

    expect(await view.findByText("ARC")).toBeTruthy();
    expect(view.getByText("Unrealized PnL")).toBeTruthy();
    expect(view.getByText("Approximate")).toBeTruthy();
    expect(view.getByText("Adjust exit")).toBeDisabled();
    expect(view.getByText("Close position")).toBeDisabled();

    fireEvent.press(view.getByText("Full details"));
    expect(onOpenDetails).toHaveBeenCalledWith("live-position-1");
    client.clear();
  });
});
