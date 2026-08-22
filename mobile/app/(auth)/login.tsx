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
import { Body, Button, Caption, ErrorNote, Field, Row } from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { useAuth } from "../../src/stores/auth";
import { colors, font, radius, shadow, space } from "../../src/theme";

export default function Login() {
  const router = useRouter();
  const setTokens = useAuth((s) => s.setTokens);
  const setUser = useAuth((s) => s.setUser);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Entrance: the wordmark and card lift in together on first paint.
  const rise = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(rise, {
      toValue: 1,
      duration: 620,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [rise]);

  const lift = (distance: number) => ({
    opacity: rise,
    transform: [
      { translateY: rise.interpolate({ inputRange: [0, 1], outputRange: [distance, 0] }) },
    ],
  });

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const tokens = await login(email.trim(), password);
      setTokens(tokens.access_token, tokens.refresh_token);
      setUser(await fetchMe());
      router.replace("/(tabs)");
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't sign you in."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={s.root}>
      {/* Ambient gradient wash behind everything */}
      <LinearGradient
        colors={["#1B1147", "#0B0F1A", "#0B0F1A"]}
        start={{ x: 0.1, y: 0 }}
        end={{ x: 0.9, y: 0.75 }}
        style={StyleSheet.absoluteFill}
      />
      <View style={s.orbViolet} />
      <View style={s.orbBlue} />

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
            <Animated.View style={[s.brandBlock, lift(26)]}>
              <View style={s.logoWrap}>
                <LinearGradient
                  colors={colors.brandGradient}
                  start={{ x: 0, y: 0 }}
                  end={{ x: 1, y: 1 }}
                  style={s.logo}
                >
                  <Text style={s.logoGlyph}>⚡</Text>
                </LinearGradient>
              </View>

              <Text style={s.wordmark}>Errandly</Text>
              <Text style={s.tagline}>Campus errands, run by students.</Text>
            </Animated.View>

            <Animated.View style={[s.card, shadow.raised, lift(40)]}>
              <Text style={s.cardTitle}>Welcome back</Text>
              <Caption style={{ marginBottom: space.lg }}>
                Sign in with your campus email.
              </Caption>

              <View style={{ gap: space.md }}>
                <Field
                  label="Email"
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
                  placeholder="••••••••"
                  value={password}
                  onChangeText={setPassword}
                  secureTextEntry
                  autoCapitalize="none"
                  returnKeyType="go"
                  onSubmitEditing={submit}
                />

                {error ? <ErrorNote>{error}</ErrorNote> : null}

                <Button
                  title="Sign in"
                  size="lg"
                  loading={busy}
                  disabled={!email.trim() || !password}
                  onPress={submit}
                  style={{ marginTop: space.xs }}
                />
              </View>
            </Animated.View>

            <Animated.View style={lift(50)}>
              <Row gap={space.xs} justify="center" style={{ marginTop: space.xl }}>
                <Body dim>New here?</Body>
                <Link href="/(auth)/register" style={s.link}>
                  Create an account
                </Link>
              </Row>
            </Animated.View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  scroll: { flexGrow: 1, justifyContent: "center", padding: space.xl },

  // Soft colour orbs give the flat background depth without an image.
  orbViolet: {
    position: "absolute",
    top: -110,
    left: -70,
    width: 300,
    height: 300,
    borderRadius: 150,
    backgroundColor: "rgba(124,92,255,0.22)",
  },
  orbBlue: {
    position: "absolute",
    top: 130,
    right: -110,
    width: 260,
    height: 260,
    borderRadius: 130,
    backgroundColor: "rgba(75,123,255,0.16)",
  },

  brandBlock: { alignItems: "center", marginBottom: space.xxl },
  logoWrap: { borderRadius: 26, ...shadow.glow(colors.brand) },
  logo: {
    width: 76,
    height: 76,
    borderRadius: 26,
    alignItems: "center",
    justifyContent: "center",
  },
  logoGlyph: { fontSize: 36 },
  wordmark: {
    color: colors.text,
    fontSize: 40,
    fontWeight: font.black,
    letterSpacing: -1.2,
    marginTop: space.lg,
  },
  tagline: { color: colors.textDim, fontSize: font.body, marginTop: space.xs },

  card: {
    backgroundColor: "rgba(21,27,43,0.92)",
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: colors.borderBright,
    padding: space.xl,
  },
  cardTitle: { color: colors.text, fontSize: font.h2, fontWeight: font.bold },

  link: { color: colors.brandBright, fontSize: font.body, fontWeight: font.bold },
});
