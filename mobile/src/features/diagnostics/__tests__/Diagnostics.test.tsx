import React from "react";
import { fireEvent, render } from "@testing-library/react-native";

import { DiagnosticsScreen } from "../DiagnosticsScreen";
import {
  redactDiagnosticPayload,
  redactDiagnosticValue,
} from "../redaction";
import type {
  MobileDiagnosticCheck,
  MobileDiagnosticsPayload,
} from "../types";

const diagnosticChecks: Array<
  [
    MobileDiagnosticCheck["id"],
    string,
    MobileDiagnosticCheck["status"],
  ]
> = [
  ["tunnel", "Private tunnel", "healthy"],
  ["api", "API", "healthy"],
  ["websocket", "WebSocket", "healthy"],
  ["token_scope", "Token scope", "healthy"],
  ["push", "Push", "warning"],
  ["telegram", "Telegram", "healthy"],
  ["clock_drift", "Clock drift", "unavailable"],
  ["snapshot_age", "Snapshot age", "healthy"],
  ["rpc", "RPC", "warning"],
  ["signer", "Signer", "blocked"],
];

const diagnostics: MobileDiagnosticsPayload = {
  artifact_type: "cryptoarc_mobile_diagnostics",
  format_version: 1,
  generated_at: "2026-07-29T14:00:00Z",
  freshness: {
    status: "fresh",
    age_seconds: 2,
    stale_after_seconds: 30,
  },
  checks: diagnosticChecks.map(([id, label, status]) => ({
    id,
    label,
    status,
    detail: `${label} status`,
    observed_at: "2026-07-29T14:00:00Z",
  })),
  recovery_actions: [
    {
      id: "reconnect",
      label: "Reconnect",
      detail: "Restore private-tunnel connectivity.",
      enabled: true,
    },
  ],
};

describe("Diagnostics and Recovery Center", () => {
  it("renders every required diagnostic status and recovery action", async () => {
    const onExport = jest.fn();
    const view = await render(
      <DiagnosticsScreen
        diagnostics={diagnostics}
        loading={false}
        error=""
        exporting={false}
        onRefresh={jest.fn()}
        onExport={onExport}
      />,
    );

    for (const label of [
      "Private tunnel",
      "API",
      "WebSocket",
      "Token scope",
      "Push",
      "Telegram",
      "Clock drift",
      "Snapshot age",
      "RPC",
      "Signer",
    ]) {
      expect(view.getByText(label)).toBeTruthy();
    }
    expect(view.getByText("Recovery center")).toBeTruthy();
    const exportButton = view.getByRole("button", {
      name: "Export redacted diagnostics",
    });
    fireEvent.press(exportButton);
    expect(onExport).toHaveBeenCalledTimes(1);
  });

  it("renders the diagnostics loading skeleton", async () => {
    const loading = await render(
      <DiagnosticsScreen
        diagnostics={null}
        loading
        error=""
        exporting={false}
        onRefresh={jest.fn()}
        onExport={jest.fn()}
      />,
    );
    expect(loading.getByLabelText("Loading diagnostics")).toBeTruthy();
  });

  it("renders diagnostics error and unavailable states", async () => {
    const unavailable = await render(
      <DiagnosticsScreen
        diagnostics={null}
        loading={false}
        error="Diagnostics unavailable"
        exporting={false}
        onRefresh={jest.fn()}
        onExport={jest.fn()}
      />,
    );
    expect(unavailable.getAllByText("Diagnostics unavailable")).toHaveLength(2);
    expect(unavailable.getByRole("alert")).toBeTruthy();
  });

  it("recursively redacts secrets, internal paths, and wallet addresses", () => {
    expect(redactDiagnosticValue("api_token", "secret")).toBe("[REDACTED]");
    const redacted = redactDiagnosticPayload({
      safe: "visible",
      nested: {
        authorization: "Bearer secret",
        signature: "transaction-signature",
        raw_tx: "serialized",
        path: "C:\\Users\\Ari\\private\\wallet.json",
        wallet_public_key: "9xSensitiveWalletAddress",
      },
      values: [{ seed_phrase: "twelve words" }],
    }) as Record<string, unknown>;
    const encoded = JSON.stringify(redacted);

    expect(redacted.safe).toBe("visible");
    expect(encoded).not.toContain("Bearer secret");
    expect(encoded).not.toContain("transaction-signature");
    expect(encoded).not.toContain("serialized");
    expect(encoded).not.toContain("C:\\Users");
    expect(encoded).not.toContain("9xSensitiveWalletAddress");
    expect(encoded).not.toContain("twelve words");
  });
});
