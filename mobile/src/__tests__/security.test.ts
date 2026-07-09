import { controlsRequireUnlock, parsePairingPayload, sanitizeReason } from "../security";

describe("mobile security helpers", () => {
  it("keeps guarded controls locked when a token is present", () => {
    expect(controlsRequireUnlock("token", true)).toBe(true);
    expect(controlsRequireUnlock("token", false)).toBe(false);
    expect(controlsRequireUnlock(null, true)).toBe(false);
  });

  it("normalizes kill switch reasons", () => {
    expect(sanitizeReason(" leaving   desk ")).toBe("leaving desk");
  });

  it("parses QR pairing payloads", () => {
    expect(
      parsePairingPayload(
        JSON.stringify({
          pairing_id: "mpair_1",
          code: "123456",
          api_base_url: "https://cryptoarc-node.tailnet.ts.net",
        }),
      ),
    ).toEqual({
      pairingId: "mpair_1",
      code: "123456",
      apiBaseUrl: "https://cryptoarc-node.tailnet.ts.net",
    });
  });
});
