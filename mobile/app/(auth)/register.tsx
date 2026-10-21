import { useRouter } from "expo-router";
import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { register } from "../../src/api/auth";
import { Icon } from "../../src/components/icons";
import { Button, ErrorNote, Field, StepDots } from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { goBack } from "../../src/lib/nav";
import { colors, font, space } from "../../src/theme";

/**
 * How strong the password looks, as the four bars under the field. This is a
 * hint about shape only: the server is the one that decides what it accepts,
 * and this must never disagree with it about whether a password is usable.
 */
function strength(pw: string): { score: 0 | 1 | 2 | 3 | 4; label: string } {
  if (!pw) return { score: 0, label: "" };
  let n = 0;
  if (pw.length >= 8) n++;
  if (pw.length >= 12) n++;
  if (/[^A-Za-z0-9]/.test(pw)) n++;
  if (/[0-9]/.test(pw) && /[A-Za-z]/.test(pw)) n++;
  const score = Math.min(4, Math.max(1, n)) as 1 | 2 | 3 | 4;
  return { score, label: ["", "Weak", "Fair", "Strong", "Very strong"][score] };
}

export default function Register() {
  const router = useRouter();
  const [form, setForm] = useState({
    student_id: "",
    display_name: "",
    email: "",
    password: "",
    phone: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim());
  const complete =
    form.student_id.trim().length >= 3 &&
    form.display_name.trim().length >= 1 &&
    emailOk &&
    form.password.length >= 8;

  const pw = strength(form.password);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const { devOtp } = await register({
        student_id: form.student_id.trim(),
        display_name: form.display_name.trim(),
        email: form.email.trim(),
        password: form.password,
        phone: form.phone.trim() || undefined,
      });
      router.push({
        pathname: "/(auth)/verify",
        params: { email: form.email.trim(), devOtp: devOtp ?? "" },
      });
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't create your account."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <KeyboardAvoidingView
        style={s.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
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
          <StepDots total={3} done={1} />
        </View>

        <ScrollView
          style={s.flex}
          contentContainerStyle={s.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <Text style={s.title}>Create your{"\n"}account</Text>
          <Text style={s.sub}>
            Students only. We send a six digit code to your university email to confirm it is you.
          </Text>

          <View style={{ gap: 14, marginTop: 22 }}>
            <Field
              label="Full name"
              placeholder="Priya Sharma"
              value={form.display_name}
              onChangeText={set("display_name")}
              autoCapitalize="words"
            />

            <View style={{ flexDirection: "row", gap: 12 }}>
              <View style={s.flex}>
                <Field
                  label="Student ID"
                  placeholder="23BCE0001"
                  value={form.student_id}
                  onChangeText={set("student_id")}
                  autoCapitalize="characters"
                  mono
                />
              </View>
              <View style={{ width: 118 }}>
                <Field
                  label="Phone"
                  placeholder="optional"
                  value={form.phone}
                  onChangeText={set("phone")}
                  keyboardType="phone-pad"
                />
              </View>
            </View>

            <View>
              <Field
                label="University email"
                placeholder="you@vitstudent.ac.in"
                value={form.email}
                onChangeText={set("email")}
                autoCapitalize="none"
                keyboardType="email-address"
              />
              {emailOk ? (
                <View style={s.emailTick} pointerEvents="none">
                  <Icon name="check" size={18} color={colors.credit} />
                </View>
              ) : null}
            </View>

            <View style={{ gap: 8 }}>
              <Field
                label="Password"
                placeholder="At least 8 characters"
                value={form.password}
                onChangeText={set("password")}
                secureTextEntry
                autoCapitalize="none"
                error={
                  form.password.length > 0 && form.password.length < 8
                    ? "Needs at least 8 characters."
                    : null
                }
              />
              {form.password ? (
                <View style={s.meter}>
                  <View style={s.meterBars}>
                    {[0, 1, 2, 3].map((i) => (
                      <View
                        key={i}
                        style={[
                          s.meterBar,
                          i < pw.score && { backgroundColor: colors.brand },
                        ]}
                      />
                    ))}
                  </View>
                  <Text style={s.meterLabel}>{pw.label}</Text>
                </View>
              ) : null}
            </View>

            {error ? <ErrorNote>{error}</ErrorNote> : null}
          </View>
        </ScrollView>

        <View style={s.footer}>
          <Button
            title="Send verification code"
            size="lg"
            icon="chev"
            iconRight
            loading={busy}
            disabled={!complete}
            onPress={submit}
          />
          <View style={s.altRow}>
            <Text style={s.altText}>Already have an account?</Text>
            <Pressable onPress={() => router.replace("/(auth)/login")} hitSlop={8}>
              <Text style={s.link}>Log in</Text>
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
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

  scroll: { paddingHorizontal: 24, paddingTop: 22, paddingBottom: space.xl },
  title: { color: colors.ink, fontSize: 28, fontFamily: font.black, letterSpacing: -0.9, lineHeight: 32 },
  sub: {
    color: colors.muted,
    fontSize: 14,
    fontFamily: font.regular,
    lineHeight: 22,
    marginTop: 8,
  },

  // Sits over the field's trailing edge, level with the input text.
  emailTick: { position: "absolute", right: 14, bottom: 15 },

  meter: { flexDirection: "row", alignItems: "center", gap: 8 },
  meterBars: { flex: 1, flexDirection: "row", gap: 4 },
  meterBar: { flex: 1, height: 4, borderRadius: 2, backgroundColor: colors.line },
  meterLabel: { color: colors.brand, fontSize: 11.5, fontFamily: font.bold },

  footer: {
    paddingHorizontal: 24,
    paddingTop: 16,
    paddingBottom: space.md,
    backgroundColor: colors.white,
  },
  altRow: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 6,
    marginTop: 14,
  },
  altText: { color: colors.muted, fontSize: font.small, fontFamily: font.regular },
  link: { color: colors.brand, fontSize: font.small, fontFamily: font.bold },
});
