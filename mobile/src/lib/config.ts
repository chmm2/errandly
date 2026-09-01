import { useSettings } from "../stores/settings";

/**
 * Where the FastAPI backend lives, as seen *from the client*.
 *
 * Resolved in three tiers, most specific first:
 *   1. A host the user typed in Profile → Backend.
 *   2. EXPO_PUBLIC_API_HOST, inlined at build time by EAS.
 *   3. SHARED_API — the one deployment everybody shares.
 *
 * Tier 3 used to guess a local backend: the Expo dev server's LAN IP with the
 * port swapped, or window.location.hostname on web. That guess is why the team
 * kept seeing different data from each other. Each machine running `docker
 * compose up` gets its own Postgres volume, so "localhost:8000" is a different
 * database per person — same app, same login, different errands, different
 * vendors, different wallet. Defaulting to the shared deployment instead means
 * a teammate who has never touched Docker still sees exactly what everyone
 * else sees.
 *
 * Anyone who genuinely needs their own backend (working on the API offline,
 * testing a migration) sets it in Profile → Backend; tier 1 still wins.
 *
 * These are functions, not constants, because tier 1 can change while the app
 * is running — anything reading a module-level const would keep using the old
 * host until a restart.
 */
const SHARED_API = "https://api.errandsly.in";

/** The address compiled into this build — tiers 2 and 3, no user override. */
export function defaultApiBase(): string {
  const buildTime = process.env.EXPO_PUBLIC_API_HOST;
  if (buildTime) return buildTime.replace(/\/+$/, "");

  return SHARED_API;
}

/** The address to actually use right now, user override included. */
export function apiBase(): string {
  return useSettings.getState().apiHostOverride ?? defaultApiBase();
}

/** ws:// or wss:// origin matching {@link apiBase}. */
export function wsBase(): string {
  return apiBase().replace(/^http/, "ws");
}
