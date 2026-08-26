import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { useEffect, useRef } from "react";
import { Platform } from "react-native";

import { registerPushToken, unregisterPushToken } from "../api/notifications";

/**
 * OS-level push notifications.
 *
 * The WebSocket only reaches an app that's open; this is the banner that
 * arrives with the app closed. The backend already writes every notification
 * to Postgres and fans it out over Redis — this adds Expo as a third delivery
 * path from the same place.
 */

/** Show a banner even when the app is foregrounded. */
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

/** Remembered so logout can unregister exactly this device. */
let currentToken: string | null = null;

/**
 * Why registration last failed, if it did.
 *
 * Kept because the previous version swallowed every failure into `return null`,
 * which made a dead push pipeline impossible to diagnose from the device — the
 * app looked fine and simply never received anything.
 */
let lastFailure: string | null = null;

export function getPushFailure(): string | null {
  return lastFailure;
}

export function getCurrentPushToken(): string | null {
  return currentToken;
}

/**
 * Ask for permission and hand the resulting Expo token to the backend.
 *
 * Returns null when push isn't available: a simulator, a browser, or a user
 * who declined. None of those are errors — the app works fine without it.
 */
export async function registerForPush(): Promise<string | null> {
  lastFailure = null;

  // Push needs real hardware; emulators can't receive it.
  if (Platform.OS === "web") {
    lastFailure = "Push isn't available in a browser.";
    return null;
  }
  if (!Device.isDevice) {
    lastFailure = "Push needs a physical device — emulators can't receive it.";
    return null;
  }

  try {
    // Android needs a channel before a banner will show while backgrounded.
    // The id must match what the backend sends as `channelId`.
    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "Errand updates",
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: "#FC8019",
      });
    }

    const existing = await Notifications.getPermissionsAsync();
    let status = existing.status;
    if (status !== "granted") {
      status = (await Notifications.requestPermissionsAsync()).status;
    }
    if (status !== "granted") {
      lastFailure =
        status === "denied"
          ? "Notifications are turned off for Errandly in Android settings."
          : `Notification permission was not granted (${status}).`;
      console.warn("[push]", lastFailure);
      return null;
    }

    // EAS builds need the project id explicitly; it isn't inferred off-device.
    const projectId =
      Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;

    const { data: token } = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );

    await registerPushToken(token, Platform.OS);
    currentToken = token;
    console.log("[push] registered", token.slice(0, 24) + "…");
    return token;
  } catch (err: any) {
    // Still never lets push setup break sign-in — but it says why now.
    lastFailure = err?.message ? String(err.message) : "Push registration failed.";
    console.warn("[push] registration failed:", lastFailure, err);
    return null;
  }
}

/** Called on logout so this device stops receiving the previous user's pushes. */
export async function unregisterForPush(): Promise<void> {
  if (!currentToken) return;
  try {
    await unregisterPushToken(currentToken);
  } catch {
    // Best-effort: the token is cleared locally either way.
  } finally {
    currentToken = null;
  }
}

/**
 * Registers on mount and routes taps.
 *
 * Tapping a banner should open the errand it's about — the payload carries
 * `errand_id`, put there by the backend's notification service.
 */
export function usePushNotifications(
  isSignedIn: boolean,
  onOpenErrand: (errandId: string) => void,
) {
  const openRef = useRef(onOpenErrand);
  openRef.current = onOpenErrand;

  useEffect(() => {
    if (!isSignedIn) return;
    registerForPush();
  }, [isSignedIn]);

  useEffect(() => {
    // Tapped while the app was running or backgrounded.
    const sub = Notifications.addNotificationResponseReceivedListener((response) => {
      const data = response.notification.request.content.data as { errand_id?: string };
      if (data?.errand_id) openRef.current(data.errand_id);
    });

    // Tapped while the app was closed — the response is waiting at launch.
    Notifications.getLastNotificationResponseAsync().then((response) => {
      const data = response?.notification.request.content.data as
        | { errand_id?: string }
        | undefined;
      if (data?.errand_id) openRef.current(data.errand_id);
    });

    return () => sub.remove();
  }, []);
}
