import * as LocalAuthentication from "expo-local-authentication";
import * as SecureStore from "expo-secure-store";
import { act, render, waitFor } from "@testing-library/react-native";
import React, { useEffect } from "react";

import { SessionProvider, useSession } from "../core/session/SessionProvider";
import type { MobileDevice } from "../types";

const device: MobileDevice = {
  id: "mobile-1",
  name: "Operator phone",
  platform: "android",
  scopes: ["mobile:monitor", "mobile:control"],
  created_at: "2026-08-01T12:00:00.000Z",
  last_seen_at: "2026-08-01T12:00:00.000Z",
  expires_at: "2026-09-01T12:00:00.000Z",
  revoked_at: "",
};

type SessionValue = ReturnType<typeof useSession>;

function Probe({ onValue }: { onValue(value: SessionValue): void }) {
  const value = useSession();
  useEffect(() => {
    onValue(value);
  }, [onValue, value]);
  return null;
}

describe("core session authentication after legacy adapter removal", () => {
  let session: SessionValue | undefined;

  beforeEach(() => {
    jest.clearAllMocks();
    session = undefined;
    const values = new Map<string, string>();
    jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key) => values.get(key) ?? null);
    jest.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value) => {
      values.set(key, value);
    });
    jest.mocked(SecureStore.deleteItemAsync).mockImplementation(async (key) => {
      values.delete(key);
    });
    jest.mocked(LocalAuthentication.hasHardwareAsync).mockResolvedValue(true);
    jest.mocked(LocalAuthentication.isEnrolledAsync).mockResolvedValue(true);
    jest.mocked(LocalAuthentication.authenticateAsync).mockResolvedValue({ success: true });
  });

  async function mountPairedSession() {
    const view = await render(
      <SessionProvider>
        <Probe onValue={(value) => (session = value)} />
      </SessionProvider>,
    );
    await waitFor(() => expect(session?.loading).toBe(false));
    await act(async () => {
      await session!.replaceSession("https://cryptoarc.test", "mobile-token", device);
    });
    return view;
  }

  it("uses strong Android biometrics with device-credential fallback", async () => {
    jest.mocked(LocalAuthentication.hasHardwareAsync).mockResolvedValue(false);
    jest.mocked(LocalAuthentication.isEnrolledAsync).mockResolvedValue(false);
    jest.mocked(LocalAuthentication.authenticateAsync).mockResolvedValue({ success: true });
    const view = await mountPairedSession();

    let unlocked = false;
    await act(async () => {
      unlocked = await session!.unlockControls();
    });

    expect(unlocked).toBe(true);
    expect(LocalAuthentication.authenticateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        biometricsSecurityLevel: "strong",
        disableDeviceFallback: false,
      }),
    );
    await act(async () => view.unmount());
  });

  it("stays locked when authentication is cancelled", async () => {
    jest.mocked(LocalAuthentication.authenticateAsync).mockResolvedValue({
      success: false,
      error: "user_cancel",
      warning: "",
    });
    const view = await mountPairedSession();

    await act(async () => {
      await expect(session!.unlockControls()).resolves.toBe(false);
    });

    expect(session?.locked).toBe(true);
    expect(session?.error).toBe("Controls remain locked.");
    await act(async () => view.unmount());
  });
});
