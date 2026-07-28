import type { MobileDevice } from "../../types";

export interface SecureSessionRecord {
  version: 2;
  apiBaseUrl: string;
  token: string;
  device: MobileDevice;
  savedAt: string;
}

export interface SessionState {
  record: SecureSessionRecord | null;
  generation: number;
  loading: boolean;
  locked: boolean;
  error: string;
}
