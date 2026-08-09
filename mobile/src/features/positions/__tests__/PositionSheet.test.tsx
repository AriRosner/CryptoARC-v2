import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import React from "react";
import { Animated } from "react-native";

import { fetchPositionDetail } from "../api";
import { PositionSheet } from "../PositionSheet";
import { PositionList } from "../PositionList";
import type { PositionDetail } from "../types";
import { MobileApiError } from "../../../core/api/errors";
import { useSettingsStore } from "../../../core/settings/settingsStore";

const mockBackdrop = jest.fn();
const mockModal = jest.fn();
jest.mock("@gorhom/bottom-sheet", () => {
  const ReactModule = jest.requireActual("react");
  const { View: MockView } = jest.requireActual("react-native");
  return {
    BottomSheetBackdrop: (props: unknown) => {
      mockBackdrop(props);
      return <MockView testID="position-sheet-backdrop" />;
    },
    BottomSheetModal: ReactModule.forwardRef(
      (props: {
        backdropComponent?: (props: Record<string, unknown>) => React.ReactNode;
        children?: React.ReactNode;
      }, ref: React.ForwardedRef<unknown>) => {
        mockModal(props);
        ReactModule.useImperativeHandle(ref, () => ({
          dismiss: jest.fn(),
          present: jest.fn(),
        }));
        return (
          <MockView>
            {props.backdropComponent?.({ animatedIndex: {}, animatedPosition: {}, style: {} })}
            {props.children}
          </MockView>
        );
      },
    ),
    BottomSheetScrollView: ({ children, ...props }: { children?: React.ReactNode }) => (
      <MockView testID="position-sheet-scroll" {...props}>{children}</MockView>
    ),
    BottomSheetView: ({ children }: { children?: React.ReactNode }) => <MockView>{children}</MockView>,
  };
});

jest.mock("../api", () => ({
  fetchPositionDetail: jest.fn(),
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
  version: 4,
  stop_pct: 20,
  target_pct: 40,
  prepared_close: null,
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
    useSettingsStore.setState({ motion: "expressive" });
    fetchPositionDetailMock.mockResolvedValue(detail);
  });

  it("renders sheet and shared position motion from every motion mode", async () => {
    const expected = {
      expressive: { damping: 18, stiffness: 180 },
      balanced: { damping: 22, stiffness: 220 },
      minimal: { duration: 0 },
      system: { damping: 22, stiffness: 220 },
    } as const;

    for (const mode of ["expressive", "balanced", "minimal", "system"] as const) {
      await act(async () => useSettingsStore.setState({ motion: mode }));
      mockModal.mockClear();
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const view = await render(
        <QueryClientProvider client={client}>
          <PositionSheet
            positionId={null}
            onDismiss={jest.fn()}
            onOpenDetails={jest.fn()}
            onAdjustExit={jest.fn()}
            onClose={jest.fn()}
          />
        </QueryClientProvider>,
      );
      await waitFor(() =>
        expect(mockModal).toHaveBeenCalledWith(
          expect.objectContaining({ animationConfigs: expect.objectContaining(expected[mode]) }),
        ),
      );
      await view.unmount();
      client.clear();
    }
  });

  it("enables shared position layout transitions only for expressive motion", async () => {
    useSettingsStore.setState({ motion: "expressive" });
    const expressive = await render(
      <PositionList positions={[detail]} onPress={jest.fn()} />,
    );
    expect(expressive.getByTestId("position-transition-live-position-1")).toHaveProp(
      "layout",
      expect.anything(),
    );
    await expressive.unmount();

    useSettingsStore.setState({ motion: "minimal" });
    const minimal = await render(
      <PositionList positions={[detail]} onPress={jest.fn()} />,
    );
    expect(minimal.getByTestId("position-transition-live-position-1")).not.toHaveProp(
      "layout",
    );
    await minimal.unmount();
  });

  it("bounds row choreography to eight positions and renders the remainder statically", async () => {
    const stop = jest.fn();
    const timing = jest.spyOn(Animated, "timing").mockReturnValue({
      reset: jest.fn(),
      start: jest.fn(),
      stop,
    } as ReturnType<typeof Animated.timing>);
    const positions = Array.from({ length: 10 }, (_, index) => ({
      ...detail,
      id: `live-position-${index}`,
      symbol: `ARC-${index}`,
    }));

    useSettingsStore.setState({ motion: "expressive" });
    const view = await render(
      <PositionList positions={positions} onPress={jest.fn()} />,
    );
    const choreographed = positions.slice(0, 8).map((position) =>
      Boolean(view.getByTestId(`position-transition-${position.id}`).props.layout),
    );
    const staticRows = positions.slice(8).map((position) =>
      view.getByTestId(`position-transition-${position.id}`).props.layout,
    );
    const timingCalls = timing.mock.calls.length;
    await view.unmount();
    timing.mockRestore();

    expect(choreographed).toEqual(Array(8).fill(true));
    expect(staticRows).toEqual([undefined, undefined]);
    expect(timingCalls).toBe(8);
    expect(stop).toHaveBeenCalledTimes(8);
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

  it("uses a closing backdrop and scrollable modal accessibility boundary", async () => {
    const onDismiss = jest.fn();
    const client = new QueryClient({ defaultOptions: { queries: { gcTime: 0, retry: false } } });
    const view = await render(
      <QueryClientProvider client={client}>
        <PositionSheet
          positionId="live-position-1"
          onDismiss={onDismiss}
          onOpenDetails={jest.fn()}
          onAdjustExit={jest.fn()}
          onClose={jest.fn()}
        />
      </QueryClientProvider>,
    );

    expect(await view.findByText("Full details")).toBeTruthy();
    expect(view.getByTestId("position-sheet-scroll")).toHaveProp("accessibilityViewIsModal", true);
    expect(mockBackdrop).toHaveBeenCalledWith(
      expect.objectContaining({
        appearsOnIndex: 0,
        disappearsOnIndex: -1,
        pressBehavior: "close",
      }),
    );
    fireEvent.press(view.getByLabelText("Close position sheet"));
    expect(onDismiss).toHaveBeenCalledTimes(1);
    client.clear();
  });

  it("quarantines the session when position detail returns 401", async () => {
    fetchPositionDetailMock.mockRejectedValueOnce(
      new MobileApiError("session expired", "authentication", 401, false),
    );
    const client = new QueryClient({ defaultOptions: { queries: { gcTime: 0, retry: false } } });
    const view = await render(
      <QueryClientProvider client={client}>
        <PositionSheet
          positionId="live-position-1"
          onDismiss={jest.fn()}
          onOpenDetails={jest.fn()}
          onAdjustExit={jest.fn()}
          onClose={jest.fn()}
        />
      </QueryClientProvider>,
    );

    await view.findByText("Pair this device again to view positions.");
    expect(mockRevokeSession).toHaveBeenCalledTimes(1);
    client.clear();
  });

  it("shows a scope denial without quarantining a valid session", async () => {
    fetchPositionDetailMock.mockRejectedValueOnce(
      new MobileApiError("portfolio scope required", "authorization", 403, false),
    );
    const client = new QueryClient({ defaultOptions: { queries: { gcTime: 0, retry: false } } });
    const view = await render(
      <QueryClientProvider client={client}>
        <PositionSheet
          positionId="live-position-1"
          onDismiss={jest.fn()}
          onOpenDetails={jest.fn()}
          onAdjustExit={jest.fn()}
          onClose={jest.fn()}
        />
      </QueryClientProvider>,
    );

    expect(await view.findByText("This device does not have positions access.")).toBeTruthy();
    expect(mockRevokeSession).not.toHaveBeenCalled();
    client.clear();
  });
});
