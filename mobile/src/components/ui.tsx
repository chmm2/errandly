import { LinearGradient } from "expo-linear-gradient";
import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  type PressableProps,
  type RefreshControlProps,
  ScrollView,
  type StyleProp,
  StyleSheet,
  Text,
  TextInput,
  type TextInputProps,
  type TextStyle,
  View,
  type ViewStyle,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, font, radius, shadow, space } from "../theme";

/* ------------------------------------------------------------------ layout */

/**
 * Just enough clearance that the last row clears the tab bar — no more, or the
 * page scrolls into dead space past the footer.
 */
const TAB_BAR_CLEARANCE = 24;

export function Screen({
  children,
  scroll = false,
  padded = true,
  refreshControl,
  edges = ["top"],
  bg = colors.bg,
  tabBarClearance = true,
}: {
  children: ReactNode;
  scroll?: boolean;
  padded?: boolean;
  refreshControl?: React.ReactElement<RefreshControlProps>;
  edges?: ("top" | "bottom")[];
  bg?: string;
  tabBarClearance?: boolean;
}) {
  const inner = padded ? { paddingHorizontal: space.lg } : undefined;
  const bottom = tabBarClearance ? TAB_BAR_CLEARANCE : space.xxxl;
  return (
    <SafeAreaView style={[s.screen, { backgroundColor: bg }]} edges={edges}>
      {scroll ? (
        <ScrollView
          style={s.flex}
          contentContainerStyle={[inner, { paddingBottom: bottom }]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
          refreshControl={refreshControl}
        >
          {children}
        </ScrollView>
      ) : (
        <View style={[s.flex, inner]}>{children}</View>
      )}
    </SafeAreaView>
  );
}

/**
 * The orange hero band the web app opens almost every page with
 * (`bg-gradient-to-br from-brand to-brand-dark`).
 */
export function Hero({
  title,
  subtitle,
  children,
  compact = false,
  eyebrow,
}: {
  title: string;
  subtitle?: string;
  children?: ReactNode;
  compact?: boolean;
  /** Small uppercase line above the title — gives the band a second level. */
  eyebrow?: string;
}) {
  return (
    <LinearGradient
      colors={colors.brandGradient}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={[s.hero, compact && { paddingTop: space.xl, paddingBottom: space.xl }]}
    >
      {/* Depth: two translucent discs behind the copy, so the band reads as a
          surface rather than a flat colour fill. */}
      <View style={s.heroDiscLarge} pointerEvents="none" />
      <View style={s.heroDiscSmall} pointerEvents="none" />

      {eyebrow ? <Text style={s.heroEyebrow}>{eyebrow}</Text> : null}
      <Text style={s.heroTitle}>{title}</Text>
      {subtitle ? <Text style={s.heroSub}>{subtitle}</Text> : null}
      {children}
    </LinearGradient>
  );
}

export function Row({
  children,
  gap = space.sm,
  style,
  align = "center",
  justify,
  wrap = false,
}: {
  children: ReactNode;
  gap?: number;
  style?: StyleProp<ViewStyle>;
  align?: ViewStyle["alignItems"];
  justify?: ViewStyle["justifyContent"];
  wrap?: boolean;
}) {
  return (
    <View
      style={[
        {
          flexDirection: "row",
          alignItems: align,
          justifyContent: justify,
          gap,
          flexWrap: wrap ? "wrap" : "nowrap",
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

/* -------------------------------------------------------------------- text */

type TextProps = {
  children: ReactNode;
  style?: StyleProp<TextStyle>;
  numberOfLines?: number;
};

/** `text-3xl font-extrabold` */
export function Title({ children, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.title, style]}>
      {children}
    </Text>
  );
}

/** `text-2xl font-extrabold` — section headings */
export function Heading({ children, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.heading, style]}>
      {children}
    </Text>
  );
}

export function Body({ children, muted, style, numberOfLines }: TextProps & { muted?: boolean }) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.body, muted && { color: colors.muted }, style]}>
      {children}
    </Text>
  );
}

/** `text-sm text-muted` */
export function Caption({ children, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.caption, style]}>
      {children}
    </Text>
  );
}

/** `text-sm font-semibold` form label */
export function Label({ children, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.label, style]}>
      {children}
    </Text>
  );
}

/* ------------------------------------------------------------------ chrome */

/** `rounded-2xl border border-line p-5` */
export function Card({
  children,
  style,
  onPress,
  raised = false,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
  raised?: boolean;
}) {
  const body = <View style={[s.card, raised && shadow.card, style]}>{children}</View>;
  if (!onPress) return body;
  return (
    <Pressable onPress={onPress} style={({ pressed }) => pressed && s.pressed}>
      {body}
    </Pressable>
  );
}

/** The soft-orange rounded square holding a category emoji. */
export function IconTile({ emoji, size = 48 }: { emoji: string; size?: number }) {
  return (
    <View
      style={[
        s.iconTile,
        { width: size, height: size, borderRadius: size >= 56 ? radius.xl : radius.lg },
      ]}
    >
      <Text style={{ fontSize: size * 0.5 }}>{emoji}</Text>
    </View>
  );
}

/** `rounded-full px-3 py-1.5 text-xs font-bold` pastel pill */
export function Pill({
  label,
  bg = colors.grayBg,
  color = colors.muted,
}: {
  label: string;
  bg?: string;
  color?: string;
}) {
  return (
    <View style={[s.pill, { backgroundColor: bg }]}>
      <Text style={[s.pillText, { color }]}>{label}</Text>
    </View>
  );
}

export function Divider({ style }: { style?: StyleProp<ViewStyle> }) {
  return <View style={[s.divider, style]} />;
}

/* ----------------------------------------------------------------- buttons */

type ButtonProps = PressableProps & {
  title: string;
  /** brand = filled orange · white = white-on-orange (hero CTA) · outline · ghost · success */
  variant?: "brand" | "white" | "outline" | "ghost" | "success";
  size?: "md" | "lg";
  loading?: boolean;
  full?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Button({
  title,
  variant = "brand",
  size = "md",
  loading = false,
  full = true,
  style,
  disabled,
  ...rest
}: ButtonProps) {
  const height = size === "lg" ? 54 : 46;
  const off = disabled || loading;

  const palette: Record<string, { bg: string; fg: string; border?: string }> = {
    brand: { bg: colors.brand, fg: colors.white },
    white: { bg: colors.white, fg: colors.brand },
    outline: { bg: colors.white, fg: colors.brand, border: colors.brand },
    ghost: { bg: "transparent", fg: colors.muted },
    success: { bg: colors.emerald, fg: colors.white },
  };
  const p = palette[variant];

  return (
    <Pressable
      disabled={off}
      {...rest}
      style={({ pressed }) => [
        s.btn,
        {
          height,
          backgroundColor: p.bg,
          borderRadius: radius.lg,
          borderWidth: p.border ? 1 : 0,
          borderColor: p.border,
        },
        full && { alignSelf: "stretch" },
        variant === "brand" && !off && shadow.brand,
        off && { opacity: 0.5 },
        pressed && s.pressed,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={p.fg} />
      ) : (
        <Text style={[s.btnText, { color: p.fg }, size === "lg" && { fontSize: font.h3 }]}>
          {title}
        </Text>
      )}
    </Pressable>
  );
}

/* ------------------------------------------------------------------ inputs */

export function Field({
  label,
  error,
  hint,
  style,
  ...rest
}: TextInputProps & { label?: string; error?: string | null; hint?: string }) {
  return (
    <View style={{ gap: 6 }}>
      {label ? <Label>{label}</Label> : null}
      <TextInput
        placeholderTextColor={colors.muted}
        style={[s.input, !!error && { borderColor: colors.redText }, style]}
        {...rest}
      />
      {error ? (
        <Caption style={{ color: colors.redText }}>{error}</Caption>
      ) : hint ? (
        <Caption>{hint}</Caption>
      ) : null}
    </View>
  );
}

/* ------------------------------------------------------------------ states */

export function Loading({ label }: { label?: string }) {
  return (
    <View style={s.center}>
      <ActivityIndicator size="large" color={colors.brand} />
      {label ? (
        <Body muted style={{ marginTop: space.md }}>
          {label}
        </Body>
      ) : null}
    </View>
  );
}

/** `rounded-2xl border-2 border-dashed border-line p-12 text-center text-muted` */
export function EmptyState({
  emoji,
  title,
  body,
  action,
}: {
  emoji?: string;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <View style={s.empty}>
      {emoji ? <Text style={{ fontSize: 36, marginBottom: space.sm }}>{emoji}</Text> : null}
      <Body style={{ fontFamily: font.bold, textAlign: "center" }}>{title}</Body>
      {body ? (
        <Caption style={{ textAlign: "center", marginTop: space.xs, maxWidth: 280 }}>
          {body}
        </Caption>
      ) : null}
      {action ? <View style={{ marginTop: space.lg, alignSelf: "stretch" }}>{action}</View> : null}
    </View>
  );
}

/** `rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700` */
export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <View style={s.errorNote}>
      <Text style={s.errorText}>{children}</Text>
    </View>
  );
}

/** The web footer line, kept so both clients sign off the same way. */
export function Footer() {
  return (
    <View style={s.footer}>
      <Caption style={{ textAlign: "center" }}>
        errandly · built by students, for students · VIT Vellore
      </Caption>
    </View>
  );
}

/* ------------------------------------------------------------------ styles */

const s = StyleSheet.create({
  screen: { flex: 1 },
  flex: { flex: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: space.xl },
  pressed: { opacity: 0.85 },

  hero: {
    paddingHorizontal: space.lg,
    paddingTop: space.xxl,
    paddingBottom: space.xxl,
    overflow: "hidden",
  },
  heroDiscLarge: {
    position: "absolute",
    top: -70,
    right: -60,
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: "rgba(255,255,255,0.10)",
  },
  heroDiscSmall: {
    position: "absolute",
    bottom: -50,
    left: -30,
    width: 130,
    height: 130,
    borderRadius: 65,
    backgroundColor: "rgba(255,255,255,0.08)",
  },
  heroEyebrow: {
    color: "rgba(255,255,255,0.85)",
    fontSize: font.tiny,
    fontFamily: font.bold,
    letterSpacing: 1.2,
    textTransform: "uppercase",
    marginBottom: space.xs,
  },
  heroTitle: {
    color: colors.white,
    fontSize: font.display,
    fontFamily: font.black,
    lineHeight: 38,
    letterSpacing: -0.6,
  },
  heroSub: {
    color: "rgba(255,255,255,0.92)",
    fontSize: font.body,
    fontFamily: font.regular,
    marginTop: space.sm,
    lineHeight: 21,
  },

  title: { color: colors.ink, fontSize: font.display, fontFamily: font.black, lineHeight: 38 },
  heading: { color: colors.ink, fontSize: font.h2, fontFamily: font.black },
  body: { color: colors.ink, fontSize: font.body, fontFamily: font.regular, lineHeight: 21 },
  caption: { color: colors.muted, fontSize: font.small, fontFamily: font.regular, lineHeight: 18 },
  label: { color: colors.ink, fontSize: font.small, fontFamily: font.semi },

  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: colors.line,
    padding: space.xl,
  },

  iconTile: {
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
  },

  pill: {
    paddingHorizontal: space.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    alignSelf: "flex-start",
  },
  pillText: { fontSize: font.tiny, fontFamily: font.bold },

  divider: { height: 1, backgroundColor: colors.line },

  btn: { alignItems: "center", justifyContent: "center", paddingHorizontal: space.xl },
  btnText: { fontSize: font.body, fontFamily: font.bold },

  input: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.lg,
    paddingHorizontal: space.lg,
    paddingVertical: space.md + 2,
    color: colors.ink,
    fontSize: font.body,
    fontFamily: font.regular,
  },

  empty: {
    borderRadius: radius.xl,
    borderWidth: 2,
    borderColor: colors.line,
    borderStyle: "dashed",
    paddingVertical: space.xxxl,
    paddingHorizontal: space.xl,
    alignItems: "center",
  },

  errorNote: {
    backgroundColor: colors.redBg,
    borderColor: colors.redBorder,
    borderWidth: 1,
    borderRadius: radius.lg,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  errorText: { color: colors.redText, fontSize: font.small, fontFamily: font.regular, lineHeight: 19 },

  footer: {
    borderTopWidth: 1,
    borderTopColor: colors.line,
    paddingTop: space.xl,
    paddingBottom: space.sm,
    marginTop: space.xxl,
  },
});
