import NetInfo from "@react-native-community/netinfo";
import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { type Href, router } from "expo-router";
import React, { useEffect } from "react";

import { MobileApiError } from "../api/errors";
import { useSession } from "../session/SessionProvider";
import {
  registerPushToken,
  validateNotificationDestination,
} from "../../features/alerts/api";
import type {
  MobileAlertSeverity,
  PushRegistrationContext,
  PushRoutingData,
} from "../../features/alerts/types";

export const NOTIFICATION_CHANNELS = {
  critical: { name: "Critical trading alerts", importance: 5 },
  warning: { name: "Trading warnings", importance: 4 },
  activity: { name: "Operator activity", importance: 3 },
} as const;

const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$/;
const SUBSYSTEM = /^[a-z][a-z0-9_-]{0,39}$/;
const ROUTES = [
  /^\/(?:alerts|diagnostics)$/,
  /^\/trade\/[A-Za-z0-9][A-Za-z0-9_-]{0,119}$/,
  /^\/position\/[A-Za-z0-9][A-Za-z0-9_-]{0,119}$/,
];

interface NotificationNavigationSession {
  apiBaseUrl: string;
  token: string;
  generation: number;
  locked: boolean;
  isCurrentGeneration(generation: number): boolean;
  revokeSession(expectedGeneration?: number): Promise<boolean>;
  authenticateControl(): Promise<boolean>;
}

type DestinationValidator = (
  route: string,
  options: { apiBaseUrl: string; token: string },
) => Promise<void | boolean>;

interface RegistrationSession {
  apiBaseUrl: string;
  token: string;
  generation: number;
  isCurrentGeneration(generation: number): boolean;
  revokeSession(expectedGeneration?: number): Promise<boolean>;
}

interface StartRegistrationOptions {
  projectId: string;
  session: RegistrationSession;
  register?: (
    token: string,
    context: PushRegistrationContext,
  ) => Promise<void>;
}

function validatePushData(value: unknown): PushRoutingData | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const data = value as Record<string, unknown>;
  if (
    Object.keys(data).sort().join(",") !==
    "event_id,route,severity,subsystem"
  ) {
    return null;
  }
  const eventId = String(data.event_id ?? "");
  const severity = String(data.severity ?? "") as MobileAlertSeverity;
  const subsystem = String(data.subsystem ?? "");
  const route = String(data.route ?? "");
  if (
    !IDENTIFIER.test(eventId) ||
    !["info", "warning", "danger", "error"].includes(severity) ||
    !SUBSYSTEM.test(subsystem) ||
    !ROUTES.some((pattern) => pattern.test(route))
  ) {
    return null;
  }
  return {
    event_id: eventId,
    severity,
    subsystem,
    route,
  };
}

export async function processNotificationResponse(
  value: unknown,
  session: NotificationNavigationSession,
  navigate: (route: string) => void,
  quarantine: (reason: string) => void = () => undefined,
  validateDestination: DestinationValidator = validateNotificationDestination,
): Promise<"navigated" | "quarantined" | "locked" | "stale"> {
  const data = validatePushData(value);
  if (!data) {
    quarantine("invalid_notification_route");
    return "quarantined";
  }
  const generation = session.generation;
  if (session.locked) {
    const unlocked = await session.authenticateControl();
    if (!unlocked) return "locked";
  }
  if (!session.isCurrentGeneration(generation)) return "stale";
  try {
    const valid = await validateDestination(data.route, {
      apiBaseUrl: session.apiBaseUrl,
      token: session.token,
    });
    if (valid === false) {
      quarantine("notification_destination_unavailable");
      return "quarantined";
    }
  } catch (error) {
    if (error instanceof MobileApiError && error.status === 401) {
      if (session.isCurrentGeneration(generation)) {
        await session.revokeSession(generation);
      }
      return "stale";
    }
    quarantine("notification_destination_unavailable");
    return "quarantined";
  }
  if (!session.isCurrentGeneration(generation)) return "stale";
  navigate(data.route);
  return "navigated";
}

async function configureAndroidChannels(): Promise<void> {
  await Promise.all(
    Object.entries(NOTIFICATION_CHANNELS).map(([id, channel]) =>
      Notifications.setNotificationChannelAsync(id, {
        name: channel.name,
        importance: channel.importance,
        vibrationPattern: [0, 250, 150, 250],
      }),
    ),
  );
}

export async function startNativePushRegistration({
  projectId,
  session,
  register = registerPushToken,
}: StartRegistrationOptions): Promise<() => void> {
  let active = true;
  let online = false;
  let needsRegistration = true;
  let registrationTail: Promise<void> = Promise.resolve();
  const context: PushRegistrationContext = {
    apiBaseUrl: session.apiBaseUrl,
    token: session.token,
    generation: session.generation,
  };

  const handleFailure = async (error: unknown) => {
    if (
      error instanceof MobileApiError &&
      error.status === 401 &&
      session.isCurrentGeneration(session.generation)
    ) {
      await session.revokeSession(session.generation);
      active = false;
      return;
    }
    needsRegistration = true;
  };

  const registerCurrentToken = async () => {
    if (
      !active ||
      !online ||
      !needsRegistration ||
      !session.isCurrentGeneration(session.generation)
    ) {
      return;
    }
    needsRegistration = false;
    let rawToken = "";
    try {
      const response = await Notifications.getExpoPushTokenAsync({ projectId });
      rawToken = response.data;
      if (!session.isCurrentGeneration(session.generation)) return;
      await register(rawToken, context);
    } catch (error) {
      await handleFailure(error);
    } finally {
      rawToken = "";
    }
  };

  const queueRegistration = (): Promise<void> => {
    registrationTail = registrationTail.then(
      registerCurrentToken,
      registerCurrentToken,
    );
    return registrationTail;
  };

  await configureAndroidChannels();
  const currentPermission = await Notifications.getPermissionsAsync();
  const permission = currentPermission.granted
    ? currentPermission
    : await Notifications.requestPermissionsAsync();
  if (!permission.granted) return () => undefined;

  const connectivitySubscription = NetInfo.addEventListener((state) => {
    online =
      state.isConnected === true && state.isInternetReachable !== false;
    if (online) void queueRegistration();
  });
  const rotationSubscription = Notifications.addPushTokenListener(() => {
    needsRegistration = true;
    if (online) void queueRegistration();
  });
  const currentNetwork = await NetInfo.fetch();
  online =
    currentNetwork.isConnected === true &&
    currentNetwork.isInternetReachable !== false;
  if (online) await queueRegistration();

  return () => {
    active = false;
    connectivitySubscription();
    rotationSubscription.remove();
  };
}

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: false,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export function NotificationBridge() {
  const session = useSession();

  useEffect(() => {
    if (!session.token || !session.apiBaseUrl || !session.record) return;
    let active = true;
    let cleanup: (() => void) | undefined;
    const projectId = String(
      Constants.expoConfig?.extra?.eas?.projectId ?? "",
    );
    if (!projectId) return;
    void startNativePushRegistration({
      projectId,
      session: {
        apiBaseUrl: session.apiBaseUrl,
        token: session.token,
        generation: session.generation,
        isCurrentGeneration: session.isCurrentGeneration,
        revokeSession: session.revokeSession,
      },
    })
      .then((value) => {
        if (active) cleanup = value;
        else value();
      })
      .catch(() => {
        if (active && session.isCurrentGeneration(session.generation)) {
          session.setError("Push registration is unavailable.");
        }
      });
    return () => {
      active = false;
      cleanup?.();
    };
  }, [
    session.apiBaseUrl,
    session.generation,
    session.isCurrentGeneration,
    session.record,
    session.revokeSession,
    session.setError,
    session.token,
  ]);

  useEffect(() => {
    const subscription = Notifications.addNotificationResponseReceivedListener(
      (response) => {
        void processNotificationResponse(
          response.notification.request.content.data,
          {
            apiBaseUrl: session.apiBaseUrl,
            token: session.token ?? "",
            generation: session.generation,
            locked: session.locked,
            isCurrentGeneration: session.isCurrentGeneration,
            revokeSession: session.revokeSession,
            authenticateControl: session.authenticateControl,
          },
          (route) => router.push(route as Href),
          () => session.setError("Push link was rejected."),
        );
      },
    );
    return () => subscription.remove();
  }, [
    session.generation,
    session.isCurrentGeneration,
    session.locked,
    session.revokeSession,
    session.setError,
    session.authenticateControl,
  ]);

  return null;
}
