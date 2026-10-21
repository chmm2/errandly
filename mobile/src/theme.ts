/**
 * Errandly design tokens.
 *
 * Source of truth: the "Errandly Revamp" design canvas. Every value below is
 * lifted from that document rather than invented here, so a colour that looks
 * arbitrary is arbitrary in the design too and should be changed there first.
 *
 * Deep teal ground, Plus Jakarta Sans for text, IBM Plex Mono for anything the
 * user reads as a code: registration numbers, coordinates, one-time codes.
 */

export const colors = {
  // Ground
  bg: "#FFFFFF",
  /** Page ground behind cards on the secondary tabs. */
  bgSoft: "#F7FAF9",
  surface: "#FFFFFF",

  // Brand
  brand: "#274A4C",
  brandDeep: "#16302F",
  /** Fill behind an icon or a quiet pill. */
  brandTint: "#EDF2F1",
  /** Selected-state wash, one step warmer than the tint. */
  brandWash: "#F2F7F6",
  /** Hero band: light lands top-left, so the ramp runs down and right. */
  brandGradient: ["#2F5A5B", "#274A4C", "#16302F"] as const,
  /** The wallet band is a full step deeper than the other heroes. */
  walletGradient: ["#1E3D3E", "#16302F"] as const,

  // Ink
  ink: "#17201F",
  /** Form labels and other text that sits just under full ink. */
  inkSoft: "#3E4E4C",
  muted: "#6B7A78",
  /** Captions and meta inside a dense row, a shade cooler than muted. */
  mutedCool: "#5F6E6C",

  // Lines
  line: "#E4EAE8",
  /** Divider inside a card, lighter than the card's own border. */
  hairline: "#EEF2F1",
  /** Row separator in a stacked list. */
  hairlineSoft: "#F2F5F4",
  lineStrong: "#DCE5E3",
  /** Outline buttons and dashed placeholders. */
  lineOutline: "#CBD8D6",

  white: "#FFFFFF",
  /** Neutral chip and segmented-control trough. */
  chip: "#F2F5F4",

  // Money. Copper is the only warm hue in the app, reserved for value.
  money: "#C0803C",
  /** Copper on a dark ground, where the base tone goes muddy. */
  moneyLight: "#E3B277",
  /** Copper as text on white, darkened to stay legible. */
  moneyText: "#8A4F1B",

  // Credit
  credit: "#2F7D5B",
  creditBg: "#EDF6F0",
  /** Credit on a dark ground. */
  creditLight: "#8FD3B0",

  // Caution
  caution: "#A5473C",
  cautionBg: "#FAF0EE",
  cautionBorder: "#E1D3CF",

  // Warning, used for held money and price claims
  warnBg: "#FBF6EE",
  warnBorder: "#EADFCB",
  warnText: "#8A6528",

  /** Map ground, both the real map and the drawn placeholder. */
  mapBg: "#EAF0EE",
  mapLine: "#DCE5E3",
  mapShade: "#E7EDEB",

  /** Second avatar in a stack, so overlapping circles stay distinct. */
  avatarAlt: "#DDE8E5",
} as const;

/** Translucent whites for use on the brand band. Kept here so they stay consistent. */
export const onBrand = {
  text: "rgba(255,255,255,0.78)",
  textDim: "rgba(255,255,255,0.66)",
  textFaint: "rgba(255,255,255,0.45)",
  eyebrow: "rgba(255,255,255,0.60)",
  fill: "rgba(255,255,255,0.16)",
  fillSoft: "rgba(255,255,255,0.13)",
  /** The drifting discs that give the band depth. */
  disc: "rgba(255,255,255,0.05)",
  discWarm: "rgba(192,128,60,0.13)",
  hairline: "rgba(255,255,255,0.16)",
} as const;

/**
 * Status pills. The design gives money and motion their own hues and leaves
 * everything else in the teal family, so a glance at colour alone says whether
 * a state involves cash.
 */
export const statusStyle = {
  OPEN: { label: "Waiting for a runner", bg: colors.chip, text: colors.muted },
  ACCEPTED: { label: "Runner assigned", bg: colors.brandTint, text: colors.brand },
  IN_PROGRESS: { label: "On the way", bg: colors.brandTint, text: colors.brand },
  DELIVERED: { label: "Delivered, confirm it", bg: colors.warnBg, text: colors.warnText },
  COMPLETED: { label: "Completed", bg: colors.creditBg, text: colors.credit },
  CANCELLED: { label: "Cancelled", bg: colors.chip, text: colors.muted },
  EXPIRED: { label: "Expired", bg: colors.chip, text: colors.muted },
} as const;

/** Backend category to icon name. Every glyph is drawn now, no emoji anywhere. */
export const categoryIcon = {
  FOOD: "bowl",
  GROCERY: "bag",
  PARCEL: "parcel",
  STATIONERY: "receipt",
  PHARMACY: "shield",
  CUSTOM: "gate",
} as const;

/**
 * The four ways to start an errand, in the order and wording the design's home
 * grid uses. This is a user-facing grouping, not the backend's six categories:
 * grocery, stationery and pharmacy all share one shopping-list flow.
 */
export const startOptions = [
  {
    icon: "bowl",
    name: "Food",
    desc: "Canteens, food court, night mess",
    route: "/shops" as const,
    params: { category: "FOOD" },
  },
  {
    icon: "bag",
    name: "Shopping list",
    desc: "Groceries, stationery, medicines",
    route: "/errand/new" as const,
    params: { mode: "shopping" },
  },
  {
    icon: "parcel",
    name: "Parcel pickup",
    desc: "Amazon or Flipkart collection point",
    route: "/errand/new" as const,
    params: { category: "PARCEL" },
  },
  {
    icon: "gate",
    name: "Main gate",
    desc: "Collect a delivery at the gate",
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

/**
 * The design rounds generously and consistently: the smaller the element, the
 * tighter the radius, but nothing is ever square.
 */
export const radius = {
  sm: 12,
  md: 14,
  lg: 16,
  xl: 18,
  xxl: 20,
  card: 22,
  big: 24,
  huge: 30,
  pill: 999,
} as const;

export const font = {
  regular: "PlusJakartaSans_400Regular",
  medium: "PlusJakartaSans_500Medium",
  semi: "PlusJakartaSans_600SemiBold",
  bold: "PlusJakartaSans_700Bold",
  black: "PlusJakartaSans_800ExtraBold",

  /** Anything the user reads as a code rather than as prose. */
  mono: "IBMPlexMono_400Regular",
  monoMedium: "IBMPlexMono_500Medium",

  display: 32,
  h1: 27,
  h2: 21,
  h3: 17,
  body: 15,
  small: 13,
  tiny: 11,
} as const;

/**
 * Shadows are tinted with the ink colour rather than pure black, which keeps
 * them from going grey against the teal.
 */
export const shadow = {
  card: {
    shadowColor: "#17201F",
    shadowOpacity: 0.06,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 },
    elevation: 2,
  },
  raised: {
    shadowColor: "#17201F",
    shadowOpacity: 0.14,
    shadowRadius: 26,
    shadowOffset: { width: 0, height: 14 },
    elevation: 8,
  },
  /** Under a filled brand button, so the CTA lifts off the page. */
  brand: {
    shadowColor: "#274A4C",
    shadowOpacity: 0.4,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 10 },
    elevation: 6,
  },
  /** The wallet bubble punched through the tab bar. */
  bubble: {
    shadowColor: "#274A4C",
    shadowOpacity: 0.45,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 12 },
    elevation: 10,
  },
} as const;

export function rupees(n: number): string {
  return `₹${Math.round(n)}`;
}

/** Thousands separator, for the figures large enough to need one. */
export function rupeesLong(n: number): string {
  return `₹${Math.round(n).toLocaleString("en-IN")}`;
}

export function metres(m: number | null): string | null {
  if (m == null) return null;
  return m < 950 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`;
}

/** Rough end-to-end estimate once a runner is on it, mirrors the web app. */
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
