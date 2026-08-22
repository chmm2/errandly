/**
 * Errandly design tokens — ported from the web frontend so both clients look
 * like one product. Source of truth: frontend/src/index.css (@theme block).
 *
 * Light ground, Swiggy-orange brand, Inter throughout.
 */

export const colors = {
  // Ground — white, same as the web app's body
  bg: "#FFFFFF",
  bgSoft: "#FAFAFA",
  surface: "#FFFFFF",

  // Brand (frontend: --color-brand / -dark / -soft)
  brand: "#FC8019",
  brandDark: "#E8720C",
  brandSoft: "#FFF4EA",
  /** Hero wash — matches `bg-gradient-to-br from-brand to-brand-dark`. */
  brandGradient: ["#FC8019", "#E8720C"] as const,
  /** Deeper auth-screen wash — `from-brand via-[#f2670f] to-[#c2410c]`. */
  authGradient: ["#FC8019", "#F2670F", "#C2410C"] as const,

  // Ink (frontend: --color-ink / --color-muted / --color-line)
  ink: "#282C3F",
  muted: "#686B78",
  line: "#E9E9EB",

  white: "#FFFFFF",

  // Semantic — the pastel pill palette the web app uses for statuses
  blueBg: "#EFF6FF",
  blueText: "#1D4ED8",
  amberBg: "#FFFBEB",
  amberText: "#B45309",
  purpleBg: "#FAF5FF",
  purpleText: "#7E22CE",
  greenBg: "#F0FDF4",
  greenText: "#15803D",
  grayBg: "#F3F4F6",
  redBg: "#FEF2F2",
  redText: "#B91C1C",
  redBorder: "#FECACA",
  emerald: "#059669",
} as const;

/**
 * Status pills — label and colours lifted from the web STATUS_STYLES map so
 * both clients say the same thing about the same state.
 */
export const statusStyle = {
  OPEN: { label: "Waiting for a runner", bg: colors.blueBg, text: colors.blueText },
  ACCEPTED: { label: "Runner assigned", bg: colors.amberBg, text: colors.amberText },
  IN_PROGRESS: { label: "On the way", bg: colors.brandSoft, text: colors.brandDark },
  DELIVERED: { label: "Delivered — confirm it", bg: colors.purpleBg, text: colors.purpleText },
  COMPLETED: { label: "Completed", bg: colors.greenBg, text: colors.greenText },
  CANCELLED: { label: "Cancelled", bg: colors.grayBg, text: colors.muted },
  EXPIRED: { label: "Expired", bg: colors.grayBg, text: colors.muted },
} as const;

/** Category emoji — same glyphs the web app uses. */
export const categoryIcon: Record<string, string> = {
  FOOD: "🍔",
  GROCERY: "🛒",
  PARCEL: "📦",
  STATIONERY: "📚",
  PHARMACY: "💊",
  CUSTOM: "✨",
};

/**
 * The four ways to start an errand, exactly as the web home page frames them.
 * Note this is a *user-facing* grouping, not the backend's six categories:
 * grocery, stationery and pharmacy all share one shopping-list flow.
 */
export const startOptions = [
  {
    icon: "🛒",
    name: "Shopping list",
    desc: "Groceries, stationery, medicines — list what you need",
    route: "/errand/new" as const,
    params: { mode: "shopping" },
  },
  {
    icon: "🍔",
    name: "Food",
    desc: "Canteens, food court, night mess",
    route: "/shops" as const,
    params: { category: "FOOD" },
  },
  {
    icon: "📦",
    name: "Parcel pickup",
    desc: "Amazon / Flipkart collection point",
    route: "/errand/new" as const,
    params: { category: "PARCEL" },
  },
  {
    icon: "🛺",
    name: "Main gate",
    desc: "Collect a delivery waiting at the gate",
    route: "/errand/new" as const,
    params: { category: "CUSTOM" },
  },
];

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 28,
  xxxl: 40,
} as const;

/** Matches Tailwind's rounded-xl / -2xl / -3xl / -full. */
export const radius = {
  md: 10,
  lg: 12,
  xl: 16,
  xxl: 24,
  pill: 999,
} as const;

/** Inter weights, loaded in app/_layout.tsx. */
export const font = {
  regular: "Inter_400Regular",
  medium: "Inter_500Medium",
  semi: "Inter_600SemiBold",
  bold: "Inter_700Bold",
  black: "Inter_800ExtraBold",

  display: 32,
  h1: 26,
  h2: 21,
  h3: 17,
  body: 15,
  small: 13,
  tiny: 11,
} as const;

/** Soft elevation — the web app leans on hover:shadow-md / -lg. */
export const shadow = {
  card: {
    shadowColor: "#282C3F",
    shadowOpacity: 0.07,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  raised: {
    shadowColor: "#282C3F",
    shadowOpacity: 0.13,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },
  brand: {
    shadowColor: "#FC8019",
    shadowOpacity: 0.35,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 },
    elevation: 6,
  },
} as const;

export function rupees(n: number): string {
  return `₹${Math.round(n)}`;
}

export function metres(m: number | null): string | null {
  if (m == null) return null;
  return m < 950 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`;
}

/** Rough end-to-end estimate once a runner is on it — mirrors the web app. */
export const ETA_MINUTES = 15;

export function minsAgo(iso: string): number {
  return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
}

export function timeAgo(iso: string): string {
  const m = minsAgo(iso);
  if (m === 0) return "just now";
  if (m < 60) return `${m} min ago`;
  if (m < 1440) return `${Math.floor(m / 60)}h ago`;
  return `${Math.floor(m / 1440)}d ago`;
}
