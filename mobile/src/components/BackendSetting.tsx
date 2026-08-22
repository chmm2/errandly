import { useState } from "react";
import { View } from "react-native";

import { apiBase } from "../lib/config";
import { useSettings } from "../stores/settings";
import { colors, font, space } from "../theme";
import { Body, Button, Caption, Card, Field, Row } from "./ui";

/**
 * Lets the backend address be retyped on-device.
 *
 * A release build compiles its host in, so if that address dies the app can't
 * reach anything. This has to be reachable from the LOGIN screen, not just
 * Profile — an unreachable backend means you can't sign in, and a fix buried
 * behind the sign-in wall is a fix you can never get to.
 */
export function BackendSetting({ compact = false }: { compact?: boolean }) {
  const override = useSettings((s) => s.apiHostOverride);
  const setOverride = useSettings((s) => s.setApiHostOverride);

  const [draft, setDraft] = useState(override ?? "");
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const active = apiBase();
  const usingDefault = override === null;

  /** Prove the address answers before committing to it. */
  async function testAndSave() {
    const candidate = draft.trim().replace(/\/+$/, "");
    if (!candidate) return;
    setChecking(true);
    setResult(null);
    try {
      const res = await fetch(`${candidate}/health`, { method: "GET" });
      const body = (await res.json()) as { status?: string };
      if (res.ok && body.status) {
        setOverride(candidate);
        setResult({ ok: true, text: `Connected — backend reports "${body.status}".` });
      } else {
        setResult({ ok: false, text: `Reached it, but /health returned ${res.status}.` });
      }
    } catch {
      setResult({
        ok: false,
        text: "Couldn't reach that address. Check the URL and that the server is running.",
      });
    } finally {
      setChecking(false);
    }
  }

  return (
    <Card style={{ gap: space.md, ...(compact ? { backgroundColor: colors.surfaceHigh } : {}) }}>
      <View>
        <Caption>Currently using</Caption>
        <Body style={{ fontSize: font.small, marginTop: 2 }} numberOfLines={2}>
          {active}
        </Body>
        <Caption
          style={{ marginTop: 2, color: usingDefault ? colors.textFaint : colors.brandBright }}
        >
          {usingDefault ? "built-in default" : "custom override"}
        </Caption>
      </View>

      <Field
        label="Server address"
        placeholder="https://api.errandsly.in"
        value={draft}
        onChangeText={setDraft}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        hint="Paste the current server URL if the app can't connect."
      />

      {result ? (
        <Caption style={{ color: result.ok ? colors.success : colors.danger }}>
          {result.ok ? "✓ " : "✕ "}
          {result.text}
        </Caption>
      ) : null}

      <Row gap={space.sm}>
        <Button
          title={checking ? "Testing…" : "Test & save"}
          loading={checking}
          disabled={!draft.trim()}
          onPress={testAndSave}
          style={{ flex: 1 }}
        />
        {!usingDefault ? (
          <Button
            title="Reset"
            variant="surface"
            onPress={() => {
              setOverride(null);
              setDraft("");
              setResult(null);
            }}
            style={{ flex: 1 }}
          />
        ) : null}
      </Row>
    </Card>
  );
}
