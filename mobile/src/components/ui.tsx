import { LinearGradient } from "expo-linear-gradient";
import { type ReactNode, useEffect, useRef } from "react";
import {
  ActivityIndicator,
  Animated,
  Easing,
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
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, font, onBrand, radius, shadow, space } from "../theme";
import { Icon, type IconName } from "./icons";

/* ------------------------------------------------------------------ layout */

/**
 * Just enough clearance that the last row clears the tab bar, no more, or the
 * page scrolls into dead space past the footer. The bar is taller now that the
 * wallet bubble is punched through it.
 */
const TAB_BAR_CLEARANCE = 32;

export function Screen({
  children,
  scroll = false,
  padded = true,
  refreshControl,
  edges = ["top"],
  bg = colors.bgSoft,
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
  const inner = padded ? { paddingHorizontal: space.xl + 2 } : undefined;
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
 * A translucent disc that drifts slowly behind a hero band. Two of these at
 * different sizes and phases are what stop the band reading as a flat fill.
 */
function Disc({
  size,
  top,
  bottom,
  left,
  right,
  color = onBrand.disc,
  period = 13000,
  reverse = false,
}: {
  size: number;
  top?: number;
  bottom?: number;
  left?: number;
  right?: number;
  color?: string;
  period?: number;
  reverse?: boolean;
}) {
  const t = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(t, {
          toValue: 1,
          duration: period / 2,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(t, {
          toValue: 0,
          duration: period / 2,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [t, period]);

  const dir = reverse ? -1 : 1;
  const translateX = t.interpolate({ inputRange: [0, 1], outputRange: [0, 10 * dir] });
  const translateY = t.interpolate({ inputRange: [0, 1], outputRange: [0, -14 * dir] });

  return (
    <Animated.View
      pointerEvents="none"
      style={{
        position: "absolute",
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: color,
        top,
        bottom,
        left,
        right,
        transform: [{ translateX }, { translateY }],
      }}
    />
  );
}

/**
 * An expanding ring that fades as it grows, the design's way of saying that
 * something is live: a runner moving, a code on its way, a tab listening.
 *
 * Place it inside a relatively positioned parent. Two of these with different
 * delays read as a repeating pulse rather than a single throb.
 */
export function PulseRing({
  color = colors.brand,
  width = 2,
  round = true,
  delay = 0,
  duration = 2600,
  style,
}: {
  color?: string;
  width?: number;
  /** False for a rounded square, as on the tracking card's tile. */
  round?: boolean;
  delay?: number;
  duration?: number;
  style?: StyleProp<ViewStyle>;
}) {
  const t = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.timing(t, {
        toValue: 1,
        duration,
        delay,
        easing: Easing.out(Easing.ease),
        useNativeDriver: true,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [t, delay, duration]);

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        s.fill,
        {
          borderWidth: width,
          borderColor: color,
          borderRadius: round ? 999 : radius.xl,
          opacity: t.interpolate({ inputRange: [0, 0.7, 1], outputRange: [0.55, 0, 0] }),
          transform: [
            { scale: t.interpolate({ inputRange: [0, 1], outputRange: [0.72, 1.35] }) },
          ],
        },
        style,
      ]}
    />
  );
}

/**
 * The teal band every screen opens with. `tone` picks how deep it sits: the
 * wallet is a full step darker than the rest so money reads as its own place.
 */
export function Hero({
  title,
  subtitle,
  children,
  compact = false,
  eyebrow,
  onBack,
  tone = "brand",
  right,
  topRight,
  padBottom,
  titleStyle,
}: {
  title?: string;
  subtitle?: string;
  children?: ReactNode;
  compact?: boolean;
  /** Small uppercase line above the title, gives the band a second level. */
  eyebrow?: string;
  /** Show a back control. Any screen pushed onto the stack should pass this. */
  onBack?: () => void;
  tone?: "brand" | "deep";
  /** A control pinned to the top right, level with the title. */
  right?: ReactNode;
  /** Something level with the back button, such as a status pill. */
  topRight?: ReactNode;
  /** Extra bottom padding, for bands a card is meant to overlap. */
  padBottom?: number;
  titleStyle?: StyleProp<TextStyle>;
}) {
  const deep = tone === "deep";
  // The band runs up under the status bar, as the design draws it, so it owns
  // the top inset itself. Screens that open with a Hero pass edges={[]} to
  // Screen; otherwise the inset would be painted twice, once in the page
  // colour, leaving white status bar icons on a pale strip.
  const insets = useSafeAreaInsets();
  const top = (compact ? space.lg : space.xl) + insets.top;

  return (
    <LinearGradient
      colors={deep ? colors.walletGradient : colors.brandGradient}
      start={{ x: 0.12, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={[
        s.hero,
        { paddingTop: top },
        compact && { paddingBottom: space.lg + 4 },
        padBottom != null && { paddingBottom: padBottom },
      ]}
    >
      <Disc
        size={230}
        top={-110}
        right={-70}
        color={deep ? onBrand.discWarm : onBrand.disc}
        period={14000}
      />
      <Disc size={200} bottom={-110} left={-50} period={12000} reverse />

      {onBack || topRight ? (
        <View style={s.heroBar}>
          {onBack ? (
            <Pressable
              onPress={onBack}
              hitSlop={12}
              accessibilityRole="button"
              accessibilityLabel="Go back"
              style={({ pressed }) => [s.heroBack, pressed && { opacity: 0.6 }]}
            >
              <Icon name="back" size={20} color={colors.white} />
            </Pressable>
          ) : (
            <View />
          )}
          {topRight}
        </View>
      ) : null}

      <View style={s.heroTop}>
        <View style={s.flex}>
          {eyebrow ? <Text style={s.heroEyebrow}>{eyebrow}</Text> : null}
          {title ? <Text style={[s.heroTitle, titleStyle]}>{title}</Text> : null}
          {subtitle ? <Text style={s.heroSub}>{subtitle}</Text> : null}
        </View>
        {right}
      </View>
      {children}
    </LinearGradient>
  );
}

/** A circular translucent control for use on the hero band. */
export function HeroButton({
  icon,
  onPress,
  badge,
  label,
}: {
  icon: IconName;
  onPress?: () => void;
  badge?: number;
  label?: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      hitSlop={10}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [s.heroBtn, pressed && { opacity: 0.7 }]}
    >
      <Icon name={icon} size={21} color={colors.white} />
      {badge ? (
        <View style={s.heroBadge}>
          <Text style={s.heroBadgeText}>{badge > 9 ? "9+" : badge}</Text>
        </View>
      ) : null}
    </Pressable>
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

export function Title({ children, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.title, style]}>
      {children}
    </Text>
  );
}

/** Section headings. */
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

export function Caption({ children, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.caption, style]}>
      {children}
    </Text>
  );
}

export function Label({ children, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.label, style]}>
      {children}
    </Text>
  );
}

/** Registration numbers, coordinates, codes. Anything read as a code, not prose. */
export function Mono({ children, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.mono, style]}>
      {children}
    </Text>
  );
}

/** The small uppercase tracked line that labels a group. */
export function Eyebrow({ children, style }: TextProps) {
  return <Text style={[s.eyebrow, style]}>{children}</Text>;
}

/* ------------------------------------------------------------------ chrome */

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

/** The rounded tint square holding a drawn icon. */
export function IconTile({
  icon,
  size = 46,
  bg = colors.brandTint,
  color = colors.brand,
}: {
  icon: IconName;
  size?: number;
  bg?: string;
  color?: string;
}) {
  return (
    <View
      style={[
        s.iconTile,
        {
          width: size,
          height: size,
          borderRadius: size >= 44 ? radius.lg - 1 : radius.sm,
          backgroundColor: bg,
        },
      ]}
    >
      <Icon name={icon} size={Math.round(size * 0.54)} color={color} />
    </View>
  );
}

/** A round avatar showing an initial, used wherever there is no photo. */
export function Avatar({
  name,
  size = 44,
  bg = colors.brandTint,
  color = colors.brand,
}: {
  name: string;
  size?: number;
  bg?: string;
  color?: string;
}) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: bg,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Text style={{ fontSize: size * 0.36, fontFamily: font.black, color }}>{initials}</Text>
    </View>
  );
}

export function Pill({
  label,
  bg = colors.chip,
  color = colors.muted,
  icon,
  style,
}: {
  label: string;
  bg?: string;
  color?: string;
  icon?: IconName;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[s.pill, { backgroundColor: bg }, style]}>
      {icon ? <Icon name={icon} size={13} color={color} /> : null}
      <Text style={[s.pillText, { color }]}>{label}</Text>
    </View>
  );
}

export function Divider({ style }: { style?: StyleProp<ViewStyle> }) {
  return <View style={[s.divider, style]} />;
}

/** A horizontal step counter, as used at the top of the sign-up and post flows. */
export function StepDots({ total, done }: { total: number; done: number }) {
  return (
    <View style={{ flexDirection: "row", gap: 6 }}>
      {Array.from({ length: total }, (_, i) => (
        <View
          key={i}
          style={{
            width: 24,
            height: 4,
            borderRadius: 2,
            backgroundColor: i < done ? colors.brand : colors.lineStrong,
          }}
        />
      ))}
    </View>
  );
}

/* ----------------------------------------------------------------- buttons */

type ButtonProps = PressableProps & {
  title: string;
  /** brand = filled teal · white = white-on-teal · outline · ghost · danger */
  variant?: "brand" | "white" | "outline" | "ghost" | "danger";
  size?: "md" | "lg";
  loading?: boolean;
  full?: boolean;
  icon?: IconName;
  /** Put the icon after the label, as the forward CTAs do. */
  iconRight?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Button({
  title,
  variant = "brand",
  size = "md",
  loading = false,
  full = true,
  icon,
  iconRight = false,
  style,
  disabled,
  ...rest
}: ButtonProps) {
  const height = size === "lg" ? 54 : 46;
  const off = disabled || loading;

  const palette: Record<string, { bg: string; fg: string; border?: string; width?: number }> = {
    brand: { bg: colors.brand, fg: colors.white },
    white: { bg: colors.white, fg: colors.brand },
    outline: { bg: "transparent", fg: colors.brand, border: colors.brand, width: 1.5 },
    ghost: { bg: "transparent", fg: colors.muted },
    danger: { bg: colors.caution, fg: colors.white },
  };
  const p = palette[variant];
  const glyph = icon ? <Icon name={icon} size={size === "lg" ? 19 : 17} color={p.fg} /> : null;

  return (
    <Pressable
      disabled={off}
      accessibilityRole="button"
      {...rest}
      style={({ pressed }) => [
        s.btn,
        {
          height,
          backgroundColor: p.bg,
          borderRadius: size === "lg" ? radius.lg : radius.md,
          borderWidth: p.border ? (p.width ?? 1) : 0,
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
        <>
          {!iconRight ? glyph : null}
          <Text style={[s.btnText, { color: p.fg }, size === "lg" && { fontSize: 16 }]}>
            {title}
          </Text>
          {iconRight ? glyph : null}
        </>
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
  icon,
  mono = false,
  ...rest
}: TextInputProps & {
  label?: string;
  error?: string | null;
  hint?: string;
  icon?: IconName;
  /** Use the mono face, for codes and registration numbers. */
  mono?: boolean;
}) {
  const bad = !!error;
  return (
    <View style={{ gap: 6 }}>
      {label ? <Label>{label}</Label> : null}
      <View style={[s.inputWrap, bad && { borderColor: colors.caution }]}>
        {icon ? <Icon name={icon} size={19} color={bad ? colors.caution : colors.mutedCool} /> : null}
        <TextInput
          placeholderTextColor={colors.mutedCool}
          style={[s.input, mono && { fontFamily: font.mono }, style]}
          {...rest}
        />
      </View>
      {error ? (
        <Caption style={{ color: colors.caution }}>{error}</Caption>
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

/**
 * A shimmering placeholder. The design is explicit that loading is a skeleton
 * and not a spinner, because a skeleton says what is about to arrive.
 */
export function Skeleton({
  width,
  height = 12,
  radius: r = 6,
  style,
}: {
  width?: number | `${number}%`;
  height?: number;
  radius?: number;
  style?: StyleProp<ViewStyle>;
}) {
  const t = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.timing(t, {
        toValue: 1,
        duration: 1300,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [t]);

  const opacity = t.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: [0.45, 1, 0.45],
  });

  return (
    <Animated.View
      style={[
        { width, height, borderRadius: r, backgroundColor: colors.mapShade, opacity },
        style,
      ]}
    />
  );
}

/** One skeleton row shaped like a list item, for lists that are still loading. */
export function SkeletonRow() {
  return (
    <View style={s.skeletonRow}>
      <Skeleton width={46} height={46} radius={15} />
      <View style={{ flex: 1, gap: 8 }}>
        <Skeleton width="72%" height={12} />
        <Skeleton width="46%" height={10} radius={5} />
      </View>
    </View>
  );
}

export function EmptyState({
  icon = "moon",
  title,
  body,
  action,
}: {
  icon?: IconName;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <View style={s.empty}>
      <View style={s.emptyIcon}>
        <Icon name={icon} size={24} color={colors.mutedCool} />
      </View>
      <Text style={s.emptyTitle}>{title}</Text>
      {body ? <Text style={s.emptyBody}>{body}</Text> : null}
      {action ? <View style={{ marginTop: space.lg, alignSelf: "stretch" }}>{action}</View> : null}
    </View>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <View style={s.errorNote}>
      <Icon name="alert" size={18} color={colors.caution} />
      <Text style={s.errorText}>{children}</Text>
    </View>
  );
}

/**
 * The amber inline notice, for anything the user should weigh rather than
 * simply acknowledge: a price claim, a dev-mode code, an unlisted item.
 */
export function Notice({
  icon = "alert",
  title,
  body,
  children,
}: {
  icon?: IconName;
  title: string;
  body?: string;
  children?: ReactNode;
}) {
  return (
    <View style={s.notice}>
      <Icon name={icon} size={19} color={colors.warnText} />
      <View style={s.flex}>
        <Text style={s.noticeTitle}>{title}</Text>
        {body ? <Text style={s.noticeBody}>{body}</Text> : null}
        {children}
      </View>
    </View>
  );
}

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
  fill: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: space.xl },
  pressed: { opacity: 0.85 },

  hero: {
    paddingHorizontal: space.xl + 2,
    paddingTop: space.xl,
    paddingBottom: space.xxl - 2,
    overflow: "hidden",
  },
  heroTop: { flexDirection: "row", alignItems: "flex-start", gap: 14 },
  heroBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 14,
  },
  heroBack: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: onBrand.fill,
    alignItems: "center",
    justifyContent: "center",
  },
  heroBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: onBrand.fill,
    alignItems: "center",
    justifyContent: "center",
  },
  heroBadge: {
    position: "absolute",
    top: -2,
    right: -2,
    minWidth: 19,
    height: 19,
    paddingHorizontal: 5,
    borderRadius: 10,
    backgroundColor: colors.white,
    borderWidth: 2,
    borderColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
  heroBadgeText: { color: colors.brand, fontSize: 10.5, fontFamily: font.black },
  heroEyebrow: {
    color: onBrand.eyebrow,
    fontSize: font.tiny,
    fontFamily: font.bold,
    letterSpacing: 1.5,
    textTransform: "uppercase",
    marginBottom: 6,
  },
  heroTitle: {
    color: colors.white,
    fontSize: font.h1,
    fontFamily: font.black,
    lineHeight: 33,
    letterSpacing: -0.9,
  },
  heroSub: {
    color: onBrand.text,
    fontSize: font.small,
    fontFamily: font.regular,
    marginTop: 7,
    lineHeight: 20,
  },

  title: {
    color: colors.ink,
    fontSize: font.display,
    fontFamily: font.black,
    lineHeight: 38,
    letterSpacing: -1,
  },
  heading: {
    color: colors.ink,
    fontSize: 18,
    fontFamily: font.black,
    letterSpacing: -0.4,
  },
  body: { color: colors.ink, fontSize: font.body, fontFamily: font.regular, lineHeight: 22 },
  caption: { color: colors.muted, fontSize: 12, fontFamily: font.regular, lineHeight: 18 },
  label: { color: colors.inkSoft, fontSize: 12, fontFamily: font.semi },
  mono: { color: colors.mutedCool, fontSize: font.tiny, fontFamily: font.mono },
  eyebrow: {
    color: colors.mutedCool,
    fontSize: font.tiny,
    fontFamily: font.bold,
    letterSpacing: 1.1,
    textTransform: "uppercase",
  },

  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.card,
    borderWidth: 1,
    borderColor: colors.hairline,
    padding: space.lg,
  },

  iconTile: { alignItems: "center", justifyContent: "center" },

  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: 11,
    paddingVertical: 6,
    borderRadius: radius.pill,
    alignSelf: "flex-start",
  },
  pillText: { fontSize: font.tiny, fontFamily: font.bold },

  divider: { height: 1, backgroundColor: colors.hairline },

  btn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 9,
    paddingHorizontal: space.xl,
  },
  btnText: { fontSize: 14, fontFamily: font.bold },

  inputWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.md,
    paddingHorizontal: 14,
  },
  input: {
    flex: 1,
    paddingVertical: 13,
    color: colors.ink,
    fontSize: 14.5,
    fontFamily: font.regular,
  },

  skeletonRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.card,
    padding: 13,
  },

  empty: {
    backgroundColor: colors.surface,
    borderRadius: radius.card,
    borderWidth: 1.5,
    borderColor: colors.lineStrong,
    borderStyle: "dashed",
    paddingVertical: space.xl,
    paddingHorizontal: space.lg,
    alignItems: "center",
  },
  emptyIcon: {
    width: 46,
    height: 46,
    borderRadius: radius.lg,
    backgroundColor: colors.chip,
    alignItems: "center",
    justifyContent: "center",
  },
  emptyTitle: {
    color: colors.ink,
    fontSize: 14.5,
    fontFamily: font.bold,
    marginTop: space.md,
    textAlign: "center",
  },
  emptyBody: {
    color: colors.muted,
    fontSize: 12.5,
    fontFamily: font.regular,
    lineHeight: 19,
    marginTop: 3,
    textAlign: "center",
    maxWidth: 280,
  },

  errorNote: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
    backgroundColor: colors.cautionBg,
    borderColor: colors.cautionBorder,
    borderWidth: 1,
    borderRadius: radius.lg,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  errorText: {
    flex: 1,
    color: colors.caution,
    fontSize: font.small,
    fontFamily: font.regular,
    lineHeight: 19,
  },

  notice: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 11,
    backgroundColor: colors.warnBg,
    borderColor: colors.warnBorder,
    borderWidth: 1,
    borderRadius: radius.xl,
    padding: 14,
  },
  noticeTitle: { color: colors.ink, fontSize: 13, fontFamily: font.bold },
  noticeBody: {
    color: colors.warnText,
    fontSize: 12,
    fontFamily: font.regular,
    lineHeight: 18,
    marginTop: 2,
  },

  footer: {
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
    paddingTop: space.xl,
    paddingBottom: space.sm,
    marginTop: space.xxl,
  },
});
