import { render } from "@testing-library/react-native";
import React from "react";

import { sampleEvents } from "../../testPayloads";
import { FeedList, filterFeedEvents, summarizeFeed } from "../FeedList";

describe("FeedList", () => {
  it("filters by level and subsystem", () => {
    expect(filterFeedEvents(sampleEvents, "warning", "")).toHaveLength(1);
    expect(filterFeedEvents(sampleEvents, "", "mobile")).toHaveLength(1);
    expect(filterFeedEvents(sampleEvents, "danger", "live")[0].message).toBe("Live kill switch enabled");
  });

  it("summarizes event levels for the feed dashboard", () => {
    expect(summarizeFeed(sampleEvents)).toEqual({ danger: 1, warning: 1, info: 1, other: 0 });
  });

  it("renders operator events", async () => {
    const { getByText } = await render(<FeedList events={sampleEvents.slice(0, 1)} />);

    expect(getByText("Source degraded")).toBeTruthy();
    expect(getByText("source")).toBeTruthy();
  });
});
