import { fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { CockpitSummary } from "../CockpitSummary";
import { sampleCockpit } from "../../testPayloads";

describe("CockpitSummary", () => {
  it("renders safety blockers before controls", async () => {
    const { getAllByText, getByText } = await render(
      <CockpitSummary
        cockpit={sampleCockpit}
        locked={true}
        loading={false}
        onRefresh={jest.fn()}
        onUnlock={jest.fn()}
        onStart={jest.fn()}
        onStop={jest.fn()}
      />,
    );

    expect(getAllByText("Source health").length).toBeGreaterThan(0);
    expect(getByText("LIVE_TRADING_ENABLED is false")).toBeTruthy();
    expect(getByText("Inspect source health.")).toBeTruthy();
    expect(getByText("Unlock")).toBeTruthy();
  });

  it("does not fire start while controls are locked", async () => {
    const onStart = jest.fn();
    const { getByText } = await render(
      <CockpitSummary
        cockpit={sampleCockpit}
        locked={true}
        loading={false}
        onRefresh={jest.fn()}
        onUnlock={jest.fn()}
        onStart={onStart}
        onStop={jest.fn()}
      />,
    );

    fireEvent.press(getByText("Start"));
    expect(onStart).not.toHaveBeenCalled();
  });
});
