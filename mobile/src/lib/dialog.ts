import { Alert, Platform } from "react-native";

/**
 * Cross-platform dialogs.
 *
 * react-native-web doesn't implement `Alert` with buttons — the call is a no-op
 * there, so any confirmation silently never resolves and the action behind it
 * (log out, cancel an errand) appears broken. Route through the browser's own
 * dialogs on web and React Native's on a device.
 */

/** Tell the user something. No decision required. */
export function notify(title: string, message?: string) {
  if (Platform.OS === "web") {
    // eslint-disable-next-line no-alert
    window.alert(message ? `${title}\n\n${message}` : title);
    return;
  }
  Alert.alert(title, message);
}

/**
 * Ask the user to confirm. Resolves true if they went ahead.
 *
 * `destructive` only affects native styling; the web dialog has one look.
 */
export function confirm(
  title: string,
  message?: string,
  options?: { confirmLabel?: string; cancelLabel?: string; destructive?: boolean },
): Promise<boolean> {
  const confirmLabel = options?.confirmLabel ?? "OK";
  const cancelLabel = options?.cancelLabel ?? "Cancel";

  if (Platform.OS === "web") {
    // eslint-disable-next-line no-alert
    return Promise.resolve(window.confirm(message ? `${title}\n\n${message}` : title));
  }

  return new Promise((resolve) => {
    Alert.alert(title, message, [
      { text: cancelLabel, style: "cancel", onPress: () => resolve(false) },
      {
        text: confirmLabel,
        style: options?.destructive ? "destructive" : "default",
        onPress: () => resolve(true),
      },
    ]);
  });
}
