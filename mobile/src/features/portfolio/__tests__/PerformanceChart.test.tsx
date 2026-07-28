jest.mock("victory-native", () => ({
  CartesianChart: () => null,
  Line: () => null,
}));

jest.mock("@shopify/react-native-skia", () => ({
  Circle: () => null,
}));

import {
  buildPerformanceChartData,
  performanceChartAnimation,
} from "../PerformanceChart";
import type { PortfolioPoint } from "../types";

const series: PortfolioPoint[] = [
  {
    at: "2026-07-28T10:00:00.000Z",
    net_pnl_sol: 0.1,
    paper_pnl_sol: 0.1,
    live_pnl_sol: 0,
    current_snapshot: false,
    approximate: false,
  },
  {
    at: "2026-07-28T10:01:00.000Z",
    net_pnl_sol: 0.2,
    paper_pnl_sol: 0.2,
    live_pnl_sol: 0,
    current_snapshot: false,
    approximate: false,
  },
  {
    at: "2026-07-28T12:01:00.000Z",
    net_pnl_sol: 0.3,
    paper_pnl_sol: 0.2,
    live_pnl_sol: 0.1,
    current_snapshot: true,
    approximate: true,
  },
];

describe("PerformanceChart", () => {
  it("plots parsed timestamps and marks the approximate snapshot distinctly", () => {
    const data = buildPerformanceChartData(series);
    expect(data.map((row) => row.timestamp)).toEqual(
      series.map((point) => Date.parse(point.at)),
    );
    expect(data.map((row) => row.currentSnapshot)).toEqual([false, false, true]);
  });

  it("follows OS reduced motion when the preference is system", () => {
    expect(performanceChartAnimation("system", true)).toBeUndefined();
    expect(performanceChartAnimation("system", false)).toEqual({
      type: "timing",
      duration: 160,
    });
  });
});
