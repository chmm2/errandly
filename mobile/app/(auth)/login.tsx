import { LinearGradient } from "expo-linear-gradient";
import { Link, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  Animated,
  Easing,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { fetchMe, login } from "../../src/api/auth";
import { Icon } from "../../src/components/icons";
import { AnimatedMark } from "../../src/components/MarkAnimated";
import { Button, ErrorNote, Field } from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { useAuth } from "../../src/stores/auth";
import { colors, font, onBrand, radius, shadow, space } from "../../src/theme";

export default function Login() {
  const router = useRouter();
  const setTokens = useAuth((s) => s.setTokens);
  const setUser = useAuth((s) => s.setUser);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // A slow bob on the mark, so the screen breathes while it waits for you.
  const bob = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(bob, {
          toValue: 1,
          duration: 2750,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(bob, {
          toValue: 0,
          duration: 2750,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [bob]);

  const float = {
    transform: [{ translateY: bob.interpolate({ inputRange: [0, 1], outputRange: [0, -9] }) }],
  };

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const tokens = await login(email.trim(), password);
      setTokens(tokens.access_token, tokens.refresh_token);
      setUser(await fetchMe());
      router.replace("/(tabs)");
    } catch (err) {
      setError(apiErrorMessage(err, "Login failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={s.root}>
      {/* The design's radial wash, with the light source at the top left.
          React Native has no radial gradient, so this runs the same three
          stops along that diagonal instead. */}
      <LinearGradient
        colors={colors.brandGradient}
        locations={[0, 0.46, 1]}
        start={{ x: 0.12, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      <View style={s.discCool} pointerEvents="none" />
      <View style={s.discWarm} pointerEvents="none" />

      <SafeAreaView style={s.flex} edges={["top", "bottom"]}>
        <KeyboardAvoidingView
          style={s.flex}
          behavior={Platform.OS === "ios" ? "padding" : undefined}
        >
          <ScrollView
            contentContainerStyle={s.scroll}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            <View style={s.brand}>
              <Animated.View style={float}>
                <AnimatedMark size={76} />
              </Animated.View>
              <Text style={s.wordmark}>errandly</Text>
              <Text style={s.pitch}>
                Campus errands, run by students you are already one degree away from.
              </Text>
            </View>

            <View style={[s.card, shadow.raised]}>
              <View style={s.cardHead}>
                <View style={s.flex}>
                  <Text style={s.cardTitle}>Welcome back</Text>
                  <Text style={s.cardSub}>Use your university email.</Text>
                </View>
                <View style={s.shield}>
                  <Icon name="shield" size={20} color={colors.brand} />
                </View>
              </View>

              <View style={{ gap: 14, marginTop: 22 }}>
                {error ? <ErrorNote>{error}</ErrorNote> : null}

                <Field
                  label="University email"
                  icon="mail"
                  placeholder="you@vitstudent.ac.in"
                  value={email}
                  onChangeText={setEmail}
                  autoCapitalize="none"
                  autoComplete="email"
                  keyboardType="email-address"
                  returnKeyType="next"
                />
                <Field
                  label="Password"
                  icon="lock"
                  placeholder="••••••••"
                  value={password}
                  onChangeText={setPassword}
                  secureTextEntry
                  autoCapitalize="none"
                  returnKeyType="go"
                  onSubmitEditing={submit}
                />

                <Button
                  title="Log in"
                  size="lg"
                  icon="chev"
                  iconRight
                  loading={busy}
                  disabled={!email.trim() || !password}
                  onPress={submit}
                />

                <Link href="/(auth)/forgot" style={s.forgot}>
                  Forgot password?
                </Link>
              </View>

              <View style={s.newHere}>
                <Text style={s.newHereText}>New here?</Text>
                <Link href="/(auth)/register" style={s.link}>
                  Create an account
                </Link>
              </View>
            </View>

            <View style={s.assurance}>
              <Icon name="shield" size={15} color={onBrand.eyebrow} />
              <Text style={s.assuranceText}>Verified students only, VIT Vellore</Text>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.brand },
  flex: { flex: 1 },
  scroll: { flexGrow: 1, justifyContent: "center", paddingHorizontal: 26, paddingVertical: 26 },

  discCool: {
    position: "absolute",
    top: -90,
    left: -80,
    width: 280,
    height: 280,
    borderRadius: 140,
    backgroundColor: onBrand.disc,
  },
  discWarm: {
    position: "absolute",
    bottom: 120,
    right: -90,
    width: 220,
    height: 220,
    borderRadius: 110,
    backgroundColor: "rgba(192,128,60,0.14)",
  },

  brand: { alignItems: "center", gap: 16, marginBottom: 26 },
  wordmark: {
    color: colors.white,
    fontSize: 31,
    fontFamily: font.black,
    letterSpacing: -1.2,
  },
  pitch: {
    color: onBrand.text,
    fontSize: font.body,
    fontFamily: font.regular,
    textAlign: "center",
    lineHeight: 23,
    maxWidth: 270,
  },

  card: {
    backgroundColor: colors.white,
    borderRadius: radius.huge,
    paddingHorizontal: 24,
    paddingTop: 28,
    paddingBottom: 24,
  },
  cardHead: { flexDirection: "row", alignItems: "center", gap: 12 },
  cardTitle: { color: colors.ink, fontSize: 23, fontFamily: font.black, letterSpacing: -0.5 },
  cardSub: { color: colors.muted, fontSize: font.small, fontFamily: font.regular, marginTop: 3 },
  shield: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.brandTint,
    alignItems: "center",
    justifyContent: "center",
  },

  newHere: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 6,
    marginTop: space.xl,
    paddingTop: 18,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
  },
  newHereText: { color: colors.muted, fontSize: font.small, fontFamily: font.regular },
  link: { color: colors.brand, fontSize: font.small, fontFamily: font.bold },
  forgot: {
    color: colors.muted,
    fontSize: font.small,
    fontFamily: font.semi,
    textAlign: "center",
  },

  assurance: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    marginTop: space.xl,
  },
  assuranceText: { color: onBrand.eyebrow, fontSize: 11.5, fontFamily: font.semi },
});
