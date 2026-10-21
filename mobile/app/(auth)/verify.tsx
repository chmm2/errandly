import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  Animated,
  Easing,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { fetchMe, resendOtp, verifyEmail } from "../../src/api/auth";
import { Icon } from "../../src/components/icons";
import { Button, ErrorNote, PulseRing, StepDots } from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { goBack } from "../../src/lib/nav";
import { useAuth } from "../../src/stores/auth";
import { colors, font, radius, space } from "../../src/theme";

const CODE_LENGTH = 6;
const RESEND_SECONDS = 24;

export default function Verify() {
  const router = useRouter();
  const params = useLocalSearchParams<{ email?: string; devOtp?: string }>();
  const email = params.email ?? "";

  const setTokens = useAuth((s) => s.setTokens);
  const setUser = useAuth((s) => s.setUser);

  const [code, setCode] = useState(params.devOtp ?? "");
  const [devOtp, setDevOtp] = useState(params.devOtp || null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);
  const [cooldown, setCooldown] = useState(RESEND_SECONDS);

  const input = useRef<TextInput>(null);
  const [focused, setFocused] = useState(false);

  // Count the resend lock down once a second. Restarted whenever a fresh code
  // goes out, so the user is never told to wait on a code they just requested.
  useEffect(() => {
    if (cooldown <= 0) return;
    const id = setInterval(() => setCooldown((n) => Math.max(0, n - 1)), 1000);
    return () => clearInterval(id);
  }, [cooldown]);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const tokens = await verifyEmail(email, code.trim());
      setTokens(tokens.access_token, tokens.refresh_token);
      setUser(await fetchMe());
      router.replace("/(tabs)");
    } catch (err) {
      setError(apiErrorMessage(err, "That code didn't work."));
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setError(null);
    setResending(true);
    try {
      const next = await resendOtp(email);
      setDevOtp(next);
      if (next) setCode(next);
      setCooldown(RESEND_SECONDS);
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't resend the code."));
    } finally {
      setResending(false);
    }
  }

  const digits = code.padEnd(CODE_LENGTH, " ").slice(0, CODE_LENGTH).split("");
  const caret = Math.min(code.length, CODE_LENGTH - 1);

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <View style={s.topBar}>
        <Pressable
          onPress={() => goBack(router, "login")}
          style={({ pressed }) => [s.back, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel="Go back"
        >
          <Icon name="back" size={21} color={colors.brand} />
        </Pressable>
        <StepDots total={3} done={2} />
      </View>

      <View style={s.head}>
        <View style={s.mailWrap}>
          <PulseRing color={colors.brand} />
          <PulseRing color={colors.brand} delay={900} />
          <View style={s.mailDisc}>
            <Icon name="mail" size={32} color={colors.brand} />
          </View>
        </View>
        <Text style={s.title}>Check your email</Text>
        <Text style={s.sub}>
          We sent a six digit code to{"\n"}
          <Text style={s.email}>{email}</Text>
        </Text>
      </View>

      {/* The boxes are the visible field; a single transparent input sitting
          over them does the actual capture, so the keyboard, paste and
          autofill all behave the way the OS expects. */}
      <Pressable style={s.boxes} onPress={() => input.current?.focus()}>
        {digits.map((d, i) => {
          const active = focused && i === caret;
          return (
            <View key={i} style={[s.box, active && s.boxActive]}>
              <Text style={s.boxText}>{d.trim()}</Text>
            </View>
          );
        })}
        <TextInput
          ref={input}
          value={code}
          onChangeText={(v) => setCode(v.replace(/\D/g, "").slice(0, CODE_LENGTH))}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          keyboardType="number-pad"
          maxLength={CODE_LENGTH}
          autoFocus
          textContentType="oneTimeCode"
          autoComplete="one-time-code"
          style={s.hiddenInput}
          accessibilityLabel="Verification code"
        />
      </Pressable>

      {devOtp ? (
        <View style={s.devNotice}>
          <Icon name="alert" size={20} color={colors.warnText} />
          <View style={{ flex: 1 }}>
            <Text style={s.devLabel}>Dev mode, email not sent</Text>
            <Text style={s.devCode}>{devOtp}</Text>
            <Text style={s.devHint}>Shown because email sending is off on the server.</Text>
          </View>
        </View>
      ) : null}

      {error ? (
        <View style={{ paddingHorizontal: 24, marginTop: space.lg }}>
          <ErrorNote>{error}</ErrorNote>
        </View>
      ) : null}

      <View style={s.flex} />

      <View style={s.footer}>
        <Button
          title="Verify and continue"
          size="lg"
          icon="check"
          iconRight
          loading={busy}
          disabled={code.trim().length < CODE_LENGTH}
          onPress={submit}
        />
        <Pressable
          onPress={resend}
          disabled={cooldown > 0 || resending}
          hitSlop={8}
          style={s.resend}
          accessibilityRole="button"
        >
          <SpinningClock stopped={cooldown === 0} />
          <Text style={s.resendText}>
            {resending
              ? "Sending a new code…"
              : cooldown > 0
                ? `Resend code in 0:${String(cooldown).padStart(2, "0")}`
                : "Resend code"}
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

/** The clock turns while the user waits and stops once the code can be resent. */
function SpinningClock({ stopped }: { stopped: boolean }) {
  const t = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (stopped) return;
    const loop = Animated.loop(
      Animated.timing(t, {
        toValue: 1,
        duration: 5000,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [t, stopped]);

  const rotate = t.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });
  return (
    <Animated.View style={{ transform: [{ rotate: stopped ? "0deg" : rotate }] }}>
      <Icon name="clock" size={17} color={colors.muted} />
    </Animated.View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.white },
  flex: { flex: 1 },

  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 24,
    paddingTop: 14,
  },
  back: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.brandTint,
    alignItems: "center",
    justifyContent: "center",
  },

  head: { paddingHorizontal: 24, paddingTop: 26, alignItems: "center" },
  mailWrap: { width: 96, height: 96, alignItems: "center", justifyContent: "center" },
  mailDisc: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.brandTint,
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    color: colors.ink,
    fontSize: 26,
    fontFamily: font.black,
    letterSpacing: -0.8,
    marginTop: space.xl,
  },
  sub: {
    color: colors.muted,
    fontSize: 14,
    fontFamily: font.regular,
    lineHeight: 22,
    marginTop: 8,
    textAlign: "center",
  },
  email: { color: colors.ink, fontFamily: font.bold },

  boxes: {
    flexDirection: "row",
    gap: 9,
    justifyContent: "center",
    paddingHorizontal: 24,
    paddingTop: 26,
  },
  box: {
    width: 48,
    height: 60,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.line,
    alignItems: "center",
    justifyContent: "center",
  },
  boxActive: {
    borderWidth: 1.5,
    borderColor: colors.brand,
    // Stands in for the design's 4px focus ring, which React Native has no
    // spread-radius equivalent for.
    shadowColor: colors.brand,
    shadowOpacity: 0.18,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 0 },
    elevation: 2,
  },
  boxText: { color: colors.ink, fontSize: 24, fontFamily: font.black },
  hiddenInput: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    opacity: 0,
    color: "transparent",
  },

  devNotice: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 12,
    marginHorizontal: 24,
    marginTop: 22,
    padding: 16,
    borderRadius: radius.xl,
    backgroundColor: colors.warnBg,
    borderWidth: 1,
    borderColor: colors.warnBorder,
  },
  devLabel: {
    color: colors.warnText,
    fontSize: 11,
    fontFamily: font.bold,
    letterSpacing: 1.1,
    textTransform: "uppercase",
  },
  devCode: {
    color: colors.ink,
    fontSize: 22,
    fontFamily: font.monoMedium,
    letterSpacing: 6,
    marginTop: 5,
    marginBottom: 3,
  },
  devHint: { color: colors.warnText, fontSize: 12, fontFamily: font.regular },

  footer: { paddingHorizontal: 24, paddingBottom: space.md, gap: 12 },
  resend: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    height: 48,
  },
  resendText: { color: colors.muted, fontSize: 14, fontFamily: font.bold },
});
