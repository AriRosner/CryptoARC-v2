jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

jest.mock("expo-local-authentication", () => ({
  hasHardwareAsync: jest.fn(async () => true),
  isEnrolledAsync: jest.fn(async () => true),
  authenticateAsync: jest.fn(async () => ({ success: true })),
}));

jest.mock("expo-notifications", () => ({
  AndroidImportance: { DEFAULT: 3, HIGH: 4, MAX: 5 },
  addNotificationReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  addNotificationResponseReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  cancelAllScheduledNotificationsAsync: jest.fn(async () => undefined),
  cancelScheduledNotificationAsync: jest.fn(async () => undefined),
  getExpoPushTokenAsync: jest.fn(async () => ({ data: "ExponentPushToken[test]" })),
  getPermissionsAsync: jest.fn(async () => ({ granted: true, status: "granted" })),
  requestPermissionsAsync: jest.fn(async () => ({ granted: true, status: "granted" })),
  scheduleNotificationAsync: jest.fn(async () => "notification-id"),
  setNotificationChannelAsync: jest.fn(async () => undefined),
  setNotificationHandler: jest.fn(),
}));

jest.mock("expo-haptics", () => ({
  ImpactFeedbackStyle: { Heavy: "heavy", Light: "light", Medium: "medium" },
  NotificationFeedbackType: { Error: "error", Success: "success", Warning: "warning" },
  impactAsync: jest.fn(async () => undefined),
  notificationAsync: jest.fn(async () => undefined),
  selectionAsync: jest.fn(async () => undefined),
}));

jest.mock("expo-sqlite", () => {
  const mockDatabase = {
    closeAsync: jest.fn(async () => undefined),
    execAsync: jest.fn(async () => undefined),
    getAllAsync: jest.fn(async () => []),
    getFirstAsync: jest.fn(async () => null),
    runAsync: jest.fn(async () => ({ changes: 0, lastInsertRowId: 0 })),
    withTransactionAsync: jest.fn(async (callback: () => Promise<unknown>) => callback()),
  };

  return {
    deleteDatabaseAsync: jest.fn(async () => undefined),
    openDatabaseAsync: jest.fn(async () => mockDatabase),
    openDatabaseSync: jest.fn(() => mockDatabase),
  };
});

jest.mock("@react-native-community/netinfo", () => {
  const mockState = {
    details: null,
    isConnected: true,
    isInternetReachable: true,
    type: "wifi",
  };
  const mockNetInfo = {
    addEventListener: jest.fn(() => jest.fn()),
    configure: jest.fn(),
    fetch: jest.fn(async () => mockState),
  };

  return {
    __esModule: true,
    addEventListener: mockNetInfo.addEventListener,
    configure: mockNetInfo.configure,
    default: mockNetInfo,
    fetch: mockNetInfo.fetch,
    useNetInfo: jest.fn(() => mockState),
  };
});

jest.mock("@shopify/react-native-skia", () => ({
  Canvas: () => null,
  Group: () => null,
  Path: () => null,
  useSharedValue: jest.fn((value: unknown) => ({ current: value })),
}));

jest.mock("@gorhom/bottom-sheet", () => ({
  BottomSheetBackdrop: () => null,
  BottomSheetModal: () => null,
  BottomSheetModalProvider: ({ children }: { children?: React.ReactNode }) => children ?? null,
  BottomSheetScrollView: ({ children }: { children?: React.ReactNode }) => children ?? null,
  BottomSheetView: ({ children }: { children?: React.ReactNode }) => children ?? null,
  default: ({ children }: { children?: React.ReactNode }) => children ?? null,
}));
