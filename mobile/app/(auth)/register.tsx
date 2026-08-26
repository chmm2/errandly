import { useRouter } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { register } from "../../src/api/auth";
import { Body, Button, Caption, ErrorNote, Field, Row, Screen, Title } from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { goBack } from "../../src/lib/nav";
import { colors, font, radius, space } from "../../src/theme";

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

  const complete =
    form.student_id.trim().length >= 3 &&
    form.display_name.trim().length >= 1 &&
    form.email.trim().length > 3 &&
    form.password.length >= 8;

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
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <Screen scroll>
        <Pressable onPress={() => goBack(router, "login")} style={s.back} hitSlop={12}>
          <Text style={s.backGlyph}>←</Text>
        </Pressable>

        <Title style={{ marginTop: space.lg }}>Create account</Title>
        <Body muted style={{ marginTop: space.xs, marginBottom: space.xxl }}>
          Students only — we verify with a code sent to your university email.
        </Body>

        <View style={{ gap: space.lg }}>
          <Field
            label="Full name"
            placeholder="Priya Sharma"
            value={form.display_name}
            onChangeText={set("display_name")}
            autoCapitalize="words"
          />
          <Field
            label="Student ID"
            placeholder="23BCE0001"
            value={form.student_id}
            onChangeText={set("student_id")}
            autoCapitalize="characters"
          />
          <Field
            label="University email"
            placeholder="you@vitstudent.ac.in"
            value={form.email}
            onChangeText={set("email")}
            autoCapitalize="none"
            keyboardType="email-address"
          />
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
          <Field
            label="Phone (optional)"
            placeholder="So your runner can reach you"
            value={form.phone}
            onChangeText={set("phone")}
            keyboardType="phone-pad"
          />

          {error ? <ErrorNote>{error}</ErrorNote> : null}

          <Button
            title="Send verification code"
            size="lg"
            loading={busy}
            disabled={!complete}
            onPress={submit}
          />

          <Row gap={4} justify="center">
            <Caption>Already have an account?</Caption>
            <Pressable onPress={() => router.replace("/(auth)/login")} hitSlop={8}>
              <Text style={s.link}>Log in</Text>
            </Pressable>
          </Row>
        </View>
      </Screen>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  back: {
    width: 42,
    height: 42,
    borderRadius: radius.pill,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
    marginTop: space.sm,
  },
  backGlyph: { color: colors.brandDark, fontSize: 19, fontFamily: font.bold },
  link: { color: colors.brand, fontSize: font.small, fontFamily: font.bold },
});
