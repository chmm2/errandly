import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { forgotPassword, resetPassword } from "../../src/api/auth";
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
import { colors, font, radius, space } from "../../src/theme";

const MIN_PASSWORD = 8; // must match RegisterRequest/ResetPasswordRequest on the backend

/**
 * Password reset, in two steps on one screen.
 *
 * Note the copy on step two: it says the code was sent "if that address has an
 * account", never that the email exists. The backend answers identically for
 * registered and unregistered addresses on purpose, and wording that implied
 * otherwise would leak exactly what that design protects.
 */
export default function Forgot() {
  const router = useRouter();

  const [step, setStep] = useState<"email" | "reset">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [devOtp, setDevOtp] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function sendCode() {
    setError(null);
    setBusy(true);
    try {
      const next = await forgotPassword(email.trim());
      setDevOtp(next);
      if (next) setCode(next);
      setStep("reset");
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't send the code. Try again."));
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      await resetPassword(email.trim(), code.trim(), password);
      setDone(true);
    } catch (err) {
      setError(apiErrorMessage(err, "That code didn't work."));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <Screen scroll>
        <Text style={s.emoji}>✅</Text>
        <Title>Password updated</Title>
        <Body muted style={{ marginTop: space.xs }}>
          You've been signed out everywhere else. Log in with your new password.
        </Body>
        <Button
          title="Back to login"
          size="lg"
          style={{ marginTop: space.xxl }}
          onPress={() => router.replace("/(auth)/login")}
        />
      </Screen>
    );
  }

  return (
    <Screen scroll>
      <Pressable
        onPress={() => (step === "reset" ? setStep("email") : router.back())}
        style={s.back}
        hitSlop={12}
      >
        <Text style={s.backGlyph}>←</Text>
      </Pressable>

      <Text style={s.emoji}>{step === "email" ? "🔑" : "📬"}</Text>

      {step === "email" ? (
        <>
          <Title>Forgot your password?</Title>
          <Body muted style={{ marginTop: space.xs }}>
            Enter your university email and we'll send you a code to set a new one.
          </Body>

          <View style={{ gap: space.lg, marginTop: space.xxl }}>
            <Field
              label="University email"
              placeholder="you@vitstudent.ac.in"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              returnKeyType="go"
              onSubmitEditing={sendCode}
            />

            {error ? <ErrorNote>{error}</ErrorNote> : null}

            <Button
              title="Send code"
              size="lg"
              loading={busy}
              disabled={!email.trim()}
              onPress={sendCode}
            />
          </View>
        </>
      ) : (
        <>
          <Title>Check your email</Title>
          <Body muted style={{ marginTop: space.xs }}>
            If{" "}
            <Text style={{ color: colors.ink, fontFamily: font.bold }}>{email.trim()}</Text>{" "}
            has an Errandly account, a 6-digit code is on its way.
          </Body>

          {devOtp ? (
            <Card style={s.devCard}>
              <Row gap={space.sm} align="flex-start">
                <Text style={{ fontSize: 16 }}>🛠️</Text>
                <View style={{ flex: 1 }}>
                  <Caption style={{ color: colors.amberText, fontFamily: font.bold }}>
                    DEV MODE — EMAIL NOT SENT
                  </Caption>
                  <Text style={s.devCode}>{devOtp}</Text>
                  <Caption>Shown because SMTP is off on the backend.</Caption>
                </View>
              </Row>
            </Card>
          ) : null}

          <View style={{ gap: space.lg, marginTop: space.xxl }}>
            <Field
              label="Reset code"
              placeholder="000000"
              value={code}
              onChangeText={setCode}
              keyboardType="number-pad"
              maxLength={8}
              style={s.codeInput}
            />
            <Field
              label="New password"
              placeholder="••••••••"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoCapitalize="none"
              returnKeyType="go"
              onSubmitEditing={submit}
              hint={`At least ${MIN_PASSWORD} characters.`}
            />

            {error ? <ErrorNote>{error}</ErrorNote> : null}

            <Button
              title="Set new password"
              size="lg"
              loading={busy}
              disabled={code.trim().length < 4 || password.length < MIN_PASSWORD}
              onPress={submit}
            />
            <Button
              title="Send a new code"
              variant="ghost"
              onPress={sendCode}
              disabled={busy}
            />
          </View>
        </>
      )}
    </Screen>
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
    marginBottom: space.xl,
  },
  backGlyph: { color: colors.brandDark, fontSize: 19, fontFamily: font.bold },
  emoji: { fontSize: 42, marginBottom: space.md },

  devCard: {
    marginTop: space.xl,
    backgroundColor: colors.amberBg,
    borderColor: "#FDE68A",
  },
  devCode: {
    color: colors.ink,
    fontSize: 28,
    fontFamily: font.black,
    letterSpacing: 7,
    marginVertical: space.xs,
  },

  codeInput: {
    fontSize: 24,
    fontFamily: font.black,
    letterSpacing: 9,
    textAlign: "center",
  },
});
