import { useRouter } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { register } from "../../src/api/auth";
import {
  Body,
  Button,
  Caption,
  ErrorNote,
  Field,
  Row,
  Screen,
  Title,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { colors, font, space } from "../../src/theme";

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
    <Screen>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <Screen scroll padded={false} edges={[]}>
          <Pressable onPress={() => router.back()} style={s.back} hitSlop={12}>
            <Text style={s.backGlyph}>←</Text>
          </Pressable>

          <Title style={{ marginTop: space.md }}>Create account</Title>
          <Body dim style={{ marginTop: space.xs, marginBottom: space.xl }}>
            Students only — we verify with a code sent to your campus email.
          </Body>

          <View style={{ gap: space.md }}>
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
              label="Campus email"
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
              hint={
                form.password.length > 0 && form.password.length < 8
                  ? undefined
                  : "Used to sign in later."
              }
              error={
                form.password.length > 0 && form.password.length < 8
                  ? "Needs at least 8 characters."
                  : null
              }
            />
            <Field
              label="Phone (optional)"
              placeholder="For runners to reach you"
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
              style={{ marginTop: space.sm }}
            />

            <Row gap={space.xs} justify="center" style={{ marginTop: space.sm }}>
              <Caption>Already have an account?</Caption>
              <Pressable onPress={() => router.replace("/(auth)/login")} hitSlop={8}>
                <Text style={s.link}>Sign in</Text>
              </Pressable>
            </Row>
          </View>
        </Screen>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const s = StyleSheet.create({
  back: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.surfaceHigh,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  backGlyph: { color: colors.text, fontSize: 20, fontWeight: font.bold },
  link: { color: colors.brandBright, fontSize: font.small, fontWeight: font.bold },
});
