import * as Haptics from "expo-haptics";

export type HapticEvent =
  | "selection"
  | "warning"
  | "rejection"
  | "confirmation";

export async function triggerHaptic(
  event: HapticEvent,
  enabled: boolean,
): Promise<void> {
  if (!enabled) return;
  try {
    if (event === "selection") {
      await Haptics.selectionAsync();
      return;
    }
    const type = {
      warning: Haptics.NotificationFeedbackType.Warning,
      rejection: Haptics.NotificationFeedbackType.Error,
      confirmation: Haptics.NotificationFeedbackType.Success,
    }[event];
    await Haptics.notificationAsync(type);
  } catch {
    // Haptics are enhancement-only and must never block an operator action.
  }
}
