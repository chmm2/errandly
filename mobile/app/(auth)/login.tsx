import { LinearGradient } from "expo-linear-gradient";
import { Link, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  Animated,
  Easing,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { fetchMe, login } from "../../src/api/auth";
import { BackendSetting } from "../../src/components/BackendSetting";
import { Button, Caption, ErrorNote, Field } from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { useAuth } from "../../src/stores/auth";
import { colors, font, radius, shadow, space } from "../../src/theme";

/** The floating errand chips from the web AuthLayout, trimmed for a phone. */
const FLOATERS = [
  { emoji: "🍜", text: "Maggi from DC · ₹30", top: 92, left: 12 },
  { emoji: "📦", text: "Parcel pickup · ₹25", top: 150, right: 10 },
];

export default function Login() {
  const router = useRouter();
  const setTokens = useAuth((s) => s.setTokens);
  const setUser = useAuth((s) => s.setUser);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showServer, setShowServer] = useState(false);

  // `animate-float` from the web app — a slow bob on the scooter mark.
  const bob = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(bob, {
          toValue: 1,
          duration: 3000,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(bob, {
          toValue: 0,
          duration: 3000,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
      ]),
    ).start();
  }, [bob]);

  const float = {
    transform: [{ translateY: bob.interpolate({ inputRange: [0, 1], outputRange: [0, -12] }) }],
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
      <LinearGradient
        colors={colors.authGradient}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      {/* Ambient shapes, same idea as the web app's blurred circles */}
      <View style={s.blobTopLeft} />
      <View style={s.blobBottomRight} />

      {FLOATERS.map((f) => (
        <View
          key={f.text}
          style={[
            s.floater,
            { top: f.top },
            f.left != null ? { left: f.left } : { right: f.right },
          ]}
        >
          <Text style={{ fontSize: 15 }}>{f.emoji}</Text>
          <Text style={s.floaterText}>{f.text}</Text>
        </View>
      ))}

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
            {/* Brand */}
            <View style={s.brand}>
              <Animated.Text style={[s.scooter, float]}>🛵</Animated.Text>
              <Text style={s.wordmark}>errandly</Text>
            </View>
            <Text style={s.pitch}>
              Campus errands,{"\n"}delivered by students.
            </Text>

            {/* Form card */}
            <View style={[s.card, shadow.raised]}>
              <Text style={s.cardTitle}>Welcome back</Text>
              <Caption style={{ marginTop: space.xs }}>
                Log in with your university email.
              </Caption>

              <View style={{ gap: space.lg, marginTop: space.xl }}>
                {error ? <ErrorNote>{error}</ErrorNote> : null}

                <Field
                  label="University email"
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

                <Button
                  title="Log in"
                  size="lg"
                  loading={busy}
                  disabled={!email.trim() || !password}
                  onPress={submit}
                />
              </View>

              <View style={s.newHere}>
                <Caption>New here? </Caption>
                <Link href="/(auth)/register" style={s.link}>
                  Create an account
                </Link>
              </View>
            </View>

            {/* Escape hatch: an unreachable server means you can't sign in, so
                the fix has to live on this side of the login wall. */}
            <Pressable onPress={() => setShowServer((v) => !v)} hitSlop={10} style={s.serverBtn}>
              <Text style={s.serverText}>
                {showServer ? "Hide server settings" : "Can't connect? Change server"}
              </Text>
            </Pressable>
            {showServer ? (
              <View style={{ marginTop: space.md }}>
                <BackendSetting compact />
              </View>
            ) : null}
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.brand },
  flex: { flex: 1 },
  scroll: { flexGrow: 1, justifyContent: "center", padding: space.xl },

  blobTopLeft: {
    position: "absolute",
    top: -110,
    left: -90,
    width: 260,
    height: 260,
    borderRadius: 130,
    backgroundColor: "rgba(255,255,255,0.10)",
  },
  blobBottomRight: {
    position: "absolute",
    bottom: -130,
    right: -80,
    width: 300,
    height: 300,
    borderRadius: 150,
    backgroundColor: "rgba(255,255,255,0.10)",
  },

  floater: {
    position: "absolute",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(255,255,255,0.18)",
    paddingHorizontal: space.md,
    paddingVertical: 7,
    borderRadius: radius.pill,
  },
  floaterText: { color: colors.white, fontSize: font.tiny, fontFamily: font.semi },

  brand: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: space.sm },
  scooter: { fontSize: 40 },
  wordmark: {
    color: colors.white,
    fontSize: 34,
    fontFamily: font.black,
    letterSpacing: -0.8,
  },
  pitch: {
    color: colors.white,
    fontSize: 25,
    fontFamily: font.black,
    textAlign: "center",
    lineHeight: 32,
    marginTop: space.lg,
    marginBottom: space.xxl,
  },

  card: {
    backgroundColor: colors.white,
    borderRadius: radius.xxl,
    padding: space.xxl,
  },
  cardTitle: { color: colors.ink, fontSize: 25, fontFamily: font.black },

  newHere: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    marginTop: space.xl,
  },
  link: { color: colors.brand, fontSize: font.small, fontFamily: font.bold },

  serverBtn: { marginTop: space.xl },
  serverText: {
    color: "rgba(255,255,255,0.85)",
    fontSize: font.small,
    fontFamily: font.semi,
    textAlign: "center",
  },
});
