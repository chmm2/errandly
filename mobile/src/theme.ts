/**
 * Errandly design tokens.
 *
 * Dark-first on purpose: this app is used walking around campus, often at
 * night, and a dark ground keeps the vivid category/reward colours doing the
 * signalling work instead of competing with a bright surface.
 */

export const colors = {
  // Ground
  bg: "#0B0F1A",
  bgElevated: "#111726",
  surface: "#151B2B",
  surfaceHigh: "#1D2537",
  surfacePressed: "#242E44",

  // Lines
  border: "#232C42",
  borderBright: "#33405E",

  // Ink
  text: "#F2F5FA",
  textDim: "#9AA6BF",
  textFaint: "#64708A",
  textOnBrand: "#FFFFFF",

  // Brand — violet→blue is the app's signature
  brand: "#7C5CFF",
  brandBright: "#9B82FF",
  brandDeep: "#4B3BD1",
  brandGradient: ["#8B6BFF", "#4B7BFF"] as const,

  // Reward / money — gold carries value everywhere in the app
  gold: "#FFB020",
  goldDeep: "#C77E00",
  goldGradient: ["#FFC84D", "#FF9500"] as const,

  // Semantic
  success: "#2FD98F",
  successDeep: "#12805098",
  warning: "#FFB020",
  danger: "#FF5F5A",
  dangerDeep: "#7A211E",
  info: "#4BB8FF",

  // Overlay
  scrim: "rgba(6, 9, 16, 0.72)",
} as const;

/** One colour + emoji per errand category, used on cards, chips and maps. */
export const categoryStyle = {
  FOOD: { label: "Food", emoji: "🍜", color: "#FF7A45", tint: "rgba(255,122,69,0.14)" },
  GROCERY: { label: "Grocery", emoji: "🛒", color: "#2FD98F", tint: "rgba(47,217,143,0.14)" },
  PARCEL: { label: "Parcel", emoji: "📦", color: "#4BB8FF", tint: "rgba(75,184,255,0.14)" },
  STATIONERY: { label: "Stationery", emoji: "✏️", color: "#FFB020", tint: "rgba(255,176,32,0.14)" },
  PHARMACY: { label: "Pharmacy", emoji: "💊", color: "#FF5F8A", tint: "rgba(255,95,138,0.14)" },
  CUSTOM: { label: "Gate pickup", emoji: "🛵", color: "#9B82FF", tint: "rgba(155,130,255,0.14)" },
} as const;

/** Colour + copy per lifecycle state — mirrors the backend's 7-state machine. */
export const statusStyle = {
  OPEN: { label: "Open", color: colors.info, tint: "rgba(75,184,255,0.14)" },
  ACCEPTED: { label: "Runner assigned", color: colors.brandBright, tint: "rgba(155,130,255,0.14)" },
  IN_PROGRESS: { label: "On the way", color: colors.gold, tint: "rgba(255,176,32,0.14)" },
  DELIVERED: { label: "Delivered", color: colors.success, tint: "rgba(47,217,143,0.14)" },
  COMPLETED: { label: "Completed", color: colors.success, tint: "rgba(47,217,143,0.14)" },
  CANCELLED: { label: "Cancelled", color: colors.danger, tint: "rgba(255,95,90,0.14)" },
  EXPIRED: { label: "Expired", color: colors.textFaint, tint: "rgba(100,112,138,0.14)" },
} as const;

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 22,
  pill: 999,
} as const;

export const font = {
  // Sizes
  display: 32,
  h1: 26,
  h2: 21,
  h3: 17,
  body: 15,
  small: 13,
  tiny: 11,
  // Weights (RN wants strings)
  black: "800" as const,
  bold: "700" as const,
  semi: "600" as const,
  regular: "400" as const,
};

/** Elevation presets — iOS shadow + Android elevation in one object. */
export const shadow = {
  card: {
    shadowColor: "#000",
    shadowOpacity: 0.35,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 },
    elevation: 6,
  },
  raised: {
    shadowColor: "#000",
    shadowOpacity: 0.45,
    shadowRadius: 22,
    shadowOffset: { width: 0, height: 10 },
    elevation: 12,
  },
  glow: (color: string) => ({
    shadowColor: color,
    shadowOpacity: 0.5,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 6 },
    elevation: 10,
  }),
} as const;

export function rupees(n: number): string {
  return `₹${Math.round(n)}`;
}

export function metres(m: number | null): string | null {
  if (m == null) return null;
  return m < 950 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`;
}

/** "3m ago" / "2h ago" — compact relative time for feeds. */
export function timeAgo(iso: string): string {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

/** Countdown to a deadline, e.g. "12m left" — null once past. */
export function timeLeft(iso: string | null): string | null {
  if (!iso) return null;
  const secs = (new Date(iso).getTime() - Date.now()) / 1000;
  if (secs <= 0) return null;
  if (secs < 60) return `${Math.floor(secs)}s left`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m left`;
  return `${Math.floor(secs / 3600)}h left`;
}
