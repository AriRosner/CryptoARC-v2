import React from "react";
import { fireEvent, render } from "@testing-library/react-native";

import {
  ActionButton,
  MetricTile,
  SegmentedControl,
  StatusBadge,
} from "../ui";

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
});
