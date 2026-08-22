import Constants from "expo-constants";

import { useSettings } from "../stores/settings";

/**
 * Where the FastAPI backend lives, as seen *from the phone*.
 *
 * Resolved in three tiers, most specific first:
 *   1. A host the user typed in Profile → Backend (survives reinstalls of the
 *      tunnel, not of the app).
 *   2. EXPO_PUBLIC_API_HOST, inlined at build time by EAS.
 *   3. The Expo dev server's own LAN IP with the port swapped — Metro on :8081
 *      means the backend is almost certainly on :8000 of the same machine.
 *
 * Tier 1 is the important one for release builds: without it the address is
 * frozen inside the APK, so any tunnel change bricks the installed app until
 * it's rebuilt and reinstalled.
 *
 * These are functions, not constants, because tier 1 can change while the app
 * is running — anything reading a module-level const would keep using the old
 * host until a restart.
 */
const BACKEND_PORT = 8000;

/** The address compiled into this build — tiers 2 and 3, no user override. */
export function defaultApiBase(): string {
  const buildTime = process.env.EXPO_PUBLIC_API_HOST;
  if (buildTime) return buildTime.replace(/\/+$/, "");

  // e.g. "192.168.1.42:8081" in dev; undefined in a production build.
  const hostUri =
    Constants.expoConfig?.hostUri ??
    (Constants.manifest2?.extra?.expoGo?.developer?.host as string | undefined);

  const lanIp = hostUri?.split(":")[0];
  if (lanIp) return `http://${lanIp}:${BACKEND_PORT}`;

  // Last resort: Android emulator's alias for the host machine's loopback.
  return `http://10.0.2.2:${BACKEND_PORT}`;
}

/** The address to actually use right now, user override included. */
export function apiBase(): string {
  return useSettings.getState().apiHostOverride ?? defaultApiBase();
}

/** ws:// or wss:// origin matching {@link apiBase}. */
export function wsBase(): string {
  return apiBase().replace(/^http/, "ws");
}
