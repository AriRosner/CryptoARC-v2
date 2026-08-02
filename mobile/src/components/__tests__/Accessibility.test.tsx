import React from "react";
import { fireEvent, render } from "@testing-library/react-native";

import {
  ActionButton,
  DetailRow,
  MetricTile,
  SegmentedControl,
  StatusBadge,
} from "../ui";
import { PositionList } from "../../features/positions/PositionList";

describe("shared accessibility contracts", () => {
  it("exposes selection state and labels for compact controls", async () => {
    const onChange = jest.fn();
    const view = await render(
      <SegmentedControl
        options={[
          { label: "1D", value: "1d" },
          { label: "ALL", value: "all" },
        ]}
        value="1d"
        onChange={onChange}
      />,
    );
    const selected = view.getByRole("button", { name: "1D" });
    expect(selected).toHaveProp("accessibilityState", { selected: true });
    fireEvent.press(view.getByRole("button", { name: "ALL" }));
    expect(onChange).toHaveBeenCalledWith("all");
  });

  it("preserves financial-action hints and visible labels", async () => {
    const view = await render(
      <ActionButton
        accessibilityHint="Reviews limits before any submission"
        label="Review withdrawal"
        onPress={jest.fn()}
      />,
    );
    expect(view.getByRole("button", { name: "Review withdrawal" })).toHaveProp(
      "accessibilityHint",
      "Reviews limits before any submission",
    );
    expect(view.getByText("Review withdrawal")).toBeTruthy();
  });

  it("announces status text so color is never the only signal", async () => {
    const view = await render(<StatusBadge label="Stale mark" tone="warning" />);
    expect(view.getByLabelText("Status: Stale mark")).toBeTruthy();
    expect(view.getByText("Stale mark")).toBeTruthy();
  });

  it("allows key labels and metric values to grow without line clipping", async () => {
    const view = await render(
      <MetricTile
        label="Current tracked value"
        value="12.842 SOL"
        detail="Approximate observation"
      />,
    );
    expect(view.getByText("Current tracked value")).not.toHaveProp("numberOfLines");
    expect(view.getByText("12.842 SOL")).not.toHaveProp("numberOfLines");
    expect(view.getByText("Approximate observation")).not.toHaveProp("numberOfLines");
  });

  it("does not cap long financial values or position symbol metadata", async () => {
    const longValue = "123456789.123456789 SOL pending reconciliation";
    const detail = await render(<DetailRow label="Tracked value" value={longValue} />);
    expect(detail.getByText(longValue)).not.toHaveProp("numberOfLines");
    await detail.unmount();

    const longSymbol = "EXTREMELY-LONG-POSITION-SYMBOL";
    const longSource = "fresh institutional pricing observation source";
    const position = await render(
      <PositionList
        positions={[{
          id: "paper:long",
          mode: "paper",
          symbol: longSymbol,
          mint: "mint-long",
          status: "open",
          opened_at: "2026-08-02T00:00:00Z",
          updated_at: "2026-08-02T00:00:00Z",
          cost_basis_sol: 1,
          value_sol: 2,
          realized_pnl_sol: 0,
          unrealized_pnl_sol: 1,
          pnl_pct: 100,
          pnl_approximate: true,
          mark_fresh: true,
          mark_age_seconds: 1,
          mark_source: longSource,
        }]}
        onPress={jest.fn()}
      />,
    );
    expect(position.getByText(longSymbol)).not.toHaveProp("numberOfLines");
    expect(position.getByText(`Fresh mark | ${longSource}`)).not.toHaveProp("numberOfLines");
    await position.unmount();
  });
});
