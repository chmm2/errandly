/**
 * Web stub.
 *
 * expo-notifications has no web implementation — importing it pulls
 * native-only modules into the bundle and breaks it outright. Metro resolves
 * this file on web instead, so every caller can stay unconditional.
 */

export function getCurrentPushToken(): string | null {
  return null;
}

export function getPushFailure(): string | null {
  return "Push isn't available in a browser.";
}

export async function registerForPush(): Promise<string | null> {
  return null;
}

export async function unregisterForPush(): Promise<void> {}

export function usePushNotifications(
  _isSignedIn: boolean,
  _onOpenErrand: (errandId: string) => void,
): void {}
