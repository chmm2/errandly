import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { forgotPassword, resetPassword } from "../../src/api/auth";
import { Icon, type IconName } from "../../src/components/icons";
import { Body, Button, ErrorNote, Field, Screen, Title } from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { goBack } from "../../src/lib/nav";
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
      <Screen scroll bg={colors.white} tabBarClearance={false}>
        <IconDisc icon="check" tone="credit" />
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
    <Screen scroll bg={colors.white} tabBarClearance={false}>
      <Pressable
        onPress={() => (step === "reset" ? setStep("email") : goBack(router, "login"))}
        style={({ pressed }) => [s.back, pressed && { opacity: 0.7 }]}
        hitSlop={12}
        accessibilityRole="button"
        accessibilityLabel="Go back"
      >
        <Icon name="back" size={21} color={colors.brand} />
      </Pressable>

      <IconDisc icon={step === "email" ? "lock" : "mail"} />

      {step === "email" ? (
        <>
          <Title>Forgot your password?</Title>
          <Body muted style={{ marginTop: space.xs }}>
            Enter your university email and we'll send you a code to set a new one.
          </Body>

          <View style={{ gap: space.lg, marginTop: space.xxl }}>
            <Field
              label="University email"
              icon="mail"
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
            <View style={s.devNotice}>
              <Icon name="alert" size={20} color={colors.warnText} />
              <View style={{ flex: 1 }}>
                <Text style={s.devLabel}>Dev mode, email not sent</Text>
                <Text style={s.devCode}>{devOtp}</Text>
                <Text style={s.devHint}>Shown because email sending is off on the server.</Text>
              </View>
            </View>
          ) : null}

          <View style={{ gap: space.lg, marginTop: space.xxl }}>
            <Field
              label="Reset code"
              mono
              placeholder="000000"
              value={code}
              onChangeText={setCode}
              keyboardType="number-pad"
              maxLength={8}
              style={s.codeInput}
            />
            <Field
              label="New password"
              icon="lock"
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

/** The round tinted badge that heads each step, in place of an emoji. */
function IconDisc({ icon, tone = "brand" }: { icon: IconName; tone?: "brand" | "credit" }) {
  const credit = tone === "credit";
  return (
    <View style={[s.disc, { backgroundColor: credit ? colors.creditBg : colors.brandTint }]}>
      <Icon name={icon} size={30} color={credit ? colors.credit : colors.brand} />
    </View>
  );
}

const s = StyleSheet.create({
  back: {
    width: 42,
    height: 42,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTint,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 14,
    marginBottom: space.xl,
  },
  disc: {
    width: 68,
    height: 68,
    borderRadius: 34,
    alignItems: "center",
    justifyContent: "center",
    marginTop: space.sm,
    marginBottom: space.lg,
  },

  devNotice: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 12,
    marginTop: space.xl,
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

  codeInput: {
    fontSize: 22,
    letterSpacing: 8,
    textAlign: "center",
  },
});
