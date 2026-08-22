import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { fetchMe, resendOtp, verifyEmail } from "../../src/api/auth";
import {
  Body,
  Button,
  Caption,
  Card,
  ErrorNote,
  Field,
  Row,
  Screen,
  Title,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { useAuth } from "../../src/stores/auth";
import { colors, font, space } from "../../src/theme";

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
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't resend the code."));
    } finally {
      setResending(false);
    }
  }

  return (
    <Screen scroll>
      <Pressable onPress={() => router.back()} style={s.back} hitSlop={12}>
        <Text style={s.backGlyph}>←</Text>
      </Pressable>

      <Text style={s.mailGlyph}>📬</Text>
      <Title>Check your email</Title>
      <Body dim style={{ marginTop: space.xs }}>
        We sent a 6-digit code to{"\n"}
        <Text style={{ color: colors.text, fontWeight: font.bold }}>{email}</Text>
      </Body>

      {devOtp ? (
        <Card style={s.devCard} glow={colors.warning}>
          <Row gap={space.sm} align="flex-start">
            <Text style={{ fontSize: 16 }}>🛠️</Text>
            <View style={{ flex: 1 }}>
              <Caption style={{ color: colors.warning, fontWeight: font.bold }}>
                DEV MODE — EMAIL NOT SENT
              </Caption>
              <Text style={s.devCode}>{devOtp}</Text>
              <Caption>Shown because SMTP is off on the backend.</Caption>
            </View>
          </Row>
        </Card>
      ) : null}

      <View style={{ gap: space.md, marginTop: space.xl }}>
        <Field
          label="Verification code"
          placeholder="000000"
          value={code}
          onChangeText={setCode}
          keyboardType="number-pad"
          maxLength={8}
          style={s.codeInput}
          returnKeyType="go"
          onSubmitEditing={submit}
        />

        {error ? <ErrorNote>{error}</ErrorNote> : null}

        <Button
          title="Verify & continue"
          size="lg"
          loading={busy}
          disabled={code.trim().length < 4}
          onPress={submit}
        />

        <Button
          title={resending ? "Sending…" : "Resend code"}
          variant="ghost"
          loading={resending}
          onPress={resend}
        />
      </View>
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
    marginBottom: space.xl,
  },
  backGlyph: { color: colors.text, fontSize: 20, fontWeight: font.bold },
  mailGlyph: { fontSize: 46, marginBottom: space.md },

  devCard: {
    marginTop: space.xl,
    backgroundColor: "rgba(255,176,32,0.08)",
    borderColor: "rgba(255,176,32,0.45)",
  },
  devCode: {
    color: colors.text,
    fontSize: 30,
    fontWeight: font.black,
    letterSpacing: 8,
    marginVertical: space.xs,
  },

  codeInput: {
    fontSize: 26,
    fontWeight: font.black,
    letterSpacing: 10,
    textAlign: "center",
  },
});
