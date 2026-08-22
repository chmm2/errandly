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

export function Screen({
  children,
  scroll = false,
  padded = true,
  refreshControl,
  edges = ["top"],
}: {
  children: ReactNode;
  scroll?: boolean;
  padded?: boolean;
  refreshControl?: React.ReactElement<RefreshControlProps>;
  edges?: ("top" | "bottom")[];
}) {
  const inner = padded ? { paddingHorizontal: space.lg } : undefined;
  return (
    <SafeAreaView style={s.screen} edges={edges}>
      {scroll ? (
        <ScrollView
          style={s.flex}
          contentContainerStyle={[inner, { paddingBottom: space.xxxl }]}
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

/** Shared shape for the text primitives. */
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

export function Heading({ children, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.heading, style]}>
      {children}
    </Text>
  );
}

export function Body({ children, dim, style, numberOfLines }: TextProps & { dim?: boolean }) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.body, dim && { color: colors.textDim }, style]}>
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

/** Small uppercase section label with letter-spacing. */
export function Label({ children, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[s.label, style]}>
      {children}
    </Text>
  );
}

/* ------------------------------------------------------------------ chrome */

export function Card({
  children,
  style,
  onPress,
  glow,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
  glow?: string;
}) {
  const body = (
    <View style={[s.card, glow ? shadow.glow(glow) : shadow.card, style]}>{children}</View>
  );
  if (!onPress) return body;
  return (
    <Pressable onPress={onPress} style={({ pressed }) => pressed && s.pressed}>
      {body}
    </Pressable>
  );
}

export function Chip({
  label,
  color = colors.textDim,
  tint = colors.surfaceHigh,
  icon,
}: {
  label: string;
  color?: string;
  tint?: string;
  icon?: string;
}) {
  return (
    <View style={[s.chip, { backgroundColor: tint }]}>
      {icon ? <Text style={s.chipIcon}>{icon}</Text> : null}
      <Text style={[s.chipText, { color }]}>{label}</Text>
    </View>
  );
}

export function Divider({ style }: { style?: StyleProp<ViewStyle> }) {
  return <View style={[s.divider, style]} />;
}

/* ----------------------------------------------------------------- buttons */

type ButtonProps = PressableProps & {
  title: string;
  variant?: "primary" | "gold" | "surface" | "danger" | "ghost";
  size?: "md" | "lg";
  loading?: boolean;
  icon?: string;
  full?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Button({
  title,
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  full = true,
  style,
  disabled,
  ...rest
}: ButtonProps) {
  const isGradient = variant === "primary" || variant === "gold";
  const height = size === "lg" ? 56 : 48;
  const off = disabled || loading;

  const content = (
    <Row gap={space.sm} justify="center">
      {loading ? (
        <ActivityIndicator color={variant === "ghost" ? colors.brandBright : colors.textOnBrand} />
      ) : (
        <>
          {icon ? <Text style={{ fontSize: 17 }}>{icon}</Text> : null}
          <Text
            style={[
              s.btnText,
              size === "lg" && { fontSize: font.h3 },
              variant === "ghost" && { color: colors.brandBright },
              variant === "surface" && { color: colors.text },
            ]}
          >
            {title}
          </Text>
        </>
      )}
    </Row>
  );

  const base: StyleProp<ViewStyle> = [
    s.btn,
    { height, borderRadius: radius.lg },
    full && { alignSelf: "stretch" },
    off && { opacity: 0.45 },
    style,
  ];

  if (isGradient) {
    const grad = variant === "gold" ? colors.goldGradient : colors.brandGradient;
    return (
      <Pressable disabled={off} {...rest} style={({ pressed }) => [base, pressed && s.pressed]}>
        <LinearGradient
          colors={grad}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={[StyleSheet.absoluteFill, { borderRadius: radius.lg }]}
        />
        {content}
      </Pressable>
    );
  }

  const flat =
    variant === "danger"
      ? { backgroundColor: colors.dangerDeep, borderColor: colors.danger, borderWidth: 1 }
      : variant === "ghost"
        ? { backgroundColor: "transparent" }
        : { backgroundColor: colors.surfaceHigh, borderColor: colors.border, borderWidth: 1 };

  return (
    <Pressable disabled={off} {...rest} style={({ pressed }) => [base, flat, pressed && s.pressed]}>
      {content}
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
    <View style={{ gap: space.xs }}>
      {label ? <Label>{label}</Label> : null}
      <TextInput
        placeholderTextColor={colors.textFaint}
        style={[s.input, !!error && { borderColor: colors.danger }, style]}
        {...rest}
      />
      {error ? (
        <Caption style={{ color: colors.danger }}>{error}</Caption>
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
      <ActivityIndicator size="large" color={colors.brandBright} />
      {label ? <Body dim style={{ marginTop: space.md }}>{label}</Body> : null}
    </View>
  );
}

export function EmptyState({
  emoji,
  title,
  body,
  action,
}: {
  emoji: string;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <View style={s.center}>
      <Text style={{ fontSize: 44, marginBottom: space.md }}>{emoji}</Text>
      <Heading style={{ textAlign: "center" }}>{title}</Heading>
      {body ? (
        <Body dim style={{ textAlign: "center", marginTop: space.xs, maxWidth: 280 }}>
          {body}
        </Body>
      ) : null}
      {action ? <View style={{ marginTop: space.lg, alignSelf: "stretch" }}>{action}</View> : null}
    </View>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <View style={s.errorNote}>
      <Text style={{ fontSize: 14 }}>⚠️</Text>
      <Text style={s.errorText}>{children}</Text>
    </View>
  );
}

/* ------------------------------------------------------------------ styles */

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: space.xl },
  pressed: { opacity: 0.72, transform: [{ scale: 0.985 }] },

  title: { color: colors.text, fontSize: font.display, fontWeight: font.black, letterSpacing: -0.5 },
  heading: { color: colors.text, fontSize: font.h2, fontWeight: font.bold, letterSpacing: -0.2 },
  body: { color: colors.text, fontSize: font.body, lineHeight: 21 },
  caption: { color: colors.textFaint, fontSize: font.small, lineHeight: 18 },
  label: {
    color: colors.textDim,
    fontSize: font.tiny,
    fontWeight: font.bold,
    letterSpacing: 1.1,
    textTransform: "uppercase",
  },

  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: colors.border,
    padding: space.lg,
  },

  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: space.md - 2,
    paddingVertical: 5,
    borderRadius: radius.pill,
  },
  chipIcon: { fontSize: 12 },
  chipText: { fontSize: font.tiny, fontWeight: font.bold, letterSpacing: 0.3 },

  divider: { height: 1, backgroundColor: colors.border },

  btn: {
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: space.xl,
    overflow: "hidden",
  },
  btnText: { color: colors.textOnBrand, fontSize: font.body, fontWeight: font.bold },

  input: {
    backgroundColor: colors.surfaceHigh,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md + 2,
    color: colors.text,
    fontSize: font.body,
  },

  errorNote: {
    flexDirection: "row",
    gap: space.sm,
    alignItems: "flex-start",
    backgroundColor: "rgba(255,95,90,0.10)",
    borderColor: "rgba(255,95,90,0.4)",
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space.md,
  },
  errorText: { color: "#FFB3B0", fontSize: font.small, flex: 1, lineHeight: 19 },
});
