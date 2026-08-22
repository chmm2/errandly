/**
 * Web no-op for push.
 *
 * expo-notifications has no web build — importing it breaks the web bundle
 * outright, so Metro picks this file up instead (a `.web.ts` sibling wins on
 * web, `push.ts` everywhere else). Browsers can't receive Expo push anyway;
 * the WebSocket already covers live updates while a tab is open.
 *
 * The exports mirror push.ts exactly so callers need no platform checks.
 */

export function getCurrentPushToken(): string | null {
  return null;
}

export async function registerForPush(): Promise<string | null> {
  return null;
}

export async function unregisterForPush(): Promise<void> {
  // nothing registered on web
}

export function usePushNotifications(
  _isSignedIn: boolean,
  _onOpenErrand: (errandId: string) => void,
): void {
  // no-op: no OS notification layer to hook into in a browser
}
