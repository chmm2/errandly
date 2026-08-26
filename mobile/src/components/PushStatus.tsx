import { useEffect, useState } from "react";
import { Linking, Platform, StyleSheet, Text, View } from "react-native";

import { getCurrentPushToken, getPushFailure, registerForPush } from "../lib/push";
import { colors, font, radius, space } from "../theme";
import { Button, Caption, Card, Row } from "./ui";

/**
 * Push status, shown only when something is wrong.
 *
 * Exists because push failed silently for a long time: registration swallowed
 * every error, so a device that never received a single notification looked
 * identical to one that was working. A dead delivery path should say so, and
 * offer the one action that fixes the common case — turning the permission
 * back on in Android settings.
 */
export function PushStatus() {
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Give registration (kicked off at sign-in) a moment to settle.
    const t = setTimeout(() => {
      if (!getCurrentPushToken()) setFailure(getPushFailure() ?? "Notifications aren't set up yet.");
    }, 1500);
    return () => clearTimeout(t);
  }, []);

  if (Platform.OS === "web") return null; // push is never available in a browser
  if (!failure) return null;

  return (
    <Card style={s.card}>
      <Row gap={space.md} align="flex-start">
        <Text style={{ fontSize: 18 }}>🔕</Text>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>Notifications are off</Text>
          <Caption style={{ marginTop: 2 }}>{failure}</Caption>
        </View>
      </Row>
      <Row gap={space.sm} style={{ marginTop: space.md }}>
        <View style={{ flex: 1 }}>
          <Button
            title="Try again"
            variant="outline"
            loading={busy}
            onPress={async () => {
              setBusy(true);
              const token = await registerForPush();
              setFailure(token ? null : (getPushFailure() ?? "Still not working."));
              setBusy(false);
            }}
          />
        </View>
        <View style={{ flex: 1 }}>
          <Button title="Open settings" onPress={() => Linking.openSettings()} />
        </View>
      </Row>
    </Card>
  );
}

const s = StyleSheet.create({
  card: {
    marginTop: space.lg,
    backgroundColor: colors.amberBg,
    borderColor: "#FDE68A",
    borderRadius: radius.xl,
  },
  title: { color: colors.ink, fontSize: font.body, fontFamily: font.bold },
});
