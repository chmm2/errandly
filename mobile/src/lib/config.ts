import Constants from "expo-constants";

/**
 * Where the FastAPI backend lives, as seen *from the phone*.
 *
 * A phone can't reach `localhost` — that resolves to the phone itself. But the
 * Expo dev server is already running on the dev machine's LAN IP, and the phone
 * had to reach it to load this bundle at all. So we reuse that host and just
 * swap the port: Metro on :8081 -> FastAPI on :8000.
 *
 * Override with EXPO_PUBLIC_API_HOST when the backend runs elsewhere (a tunnel,
 * a deployed staging box). That env var is inlined at build time by Expo.
 */
const BACKEND_PORT = 8000;

function inferHost(): string {
  const override = process.env.EXPO_PUBLIC_API_HOST;
  if (override) return override.replace(/\/+$/, "");

  // e.g. "192.168.1.42:8081" in dev; undefined in a production build.
  const hostUri =
    Constants.expoConfig?.hostUri ??
    (Constants.manifest2?.extra?.expoGo?.developer?.host as string | undefined);

  const lanIp = hostUri?.split(":")[0];
  if (lanIp) return `http://${lanIp}:${BACKEND_PORT}`;

  // Last resort: Android emulator's alias for the host machine's loopback.
  return `http://10.0.2.2:${BACKEND_PORT}`;
}

export const API_BASE = inferHost();

/** ws:// or wss:// origin for the same backend. */
export const WS_BASE = API_BASE.replace(/^http/, "ws");
