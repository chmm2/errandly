import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import type { Errand } from "../api/errands";
import { colors, font, radius, rupees, space } from "../theme";
import { Body, Button, Caption, Card, Heading } from "./ui";

/** What the order was expected to cost — the sensible starting figure. */
function expectedSpend(e: Errand): number {
  return Number(e.collect_amount || 0) + Number(e.items_total || 0);
}

/**
 * The runner states what they actually paid, as they mark the errand picked up.
 *
 * Escrow reimburses this number, so the step cannot be skipped — the headroom
 * held on every order exists precisely to cover a real price the estimate got
 * wrong, and it is unreachable until somebody says what the real price was.
 *
 * On a run with nothing to buy there is nothing to state, so the whole form
 * collapses to a plain button rather than asking a parcel courier what the
 * parcel cost them.
 */
export function PickupDeclaration({
  errand,
  busy,
  onConfirm,
}: {
  errand: Errand;
  busy: boolean;
  onConfirm: (amountSpent: number) => void;
}) {
  const expected = expectedSpend(errand);
  const [value, setValue] = useState(expected > 0 ? String(expected) : "");

  if (expected <= 0) {
    return (
      <Button
        title="Mark picked up"
        size="lg"
        loading={busy}
        onPress={() => onConfirm(0)}
      />
    );
  }

  const spent = Number(value);
  // An empty box is not zero. A blank that silently submitted the estimate
  // would defeat the point of asking at all.
  const valid = value.trim() !== "" && Number.isFinite(spent) && spent >= 0;
  const over = valid && spent > expected;

  return (
    <Card raised style={s.card}>
      <Heading style={{ fontSize: 16 }}>What did you actually pay?</Heading>
      <Caption style={{ color: colors.muted, marginTop: 2 }}>
        Estimated {rupees(expected)}. Enter the real amount from the counter — this
        is what you get reimbursed, on top of your {rupees(Number(errand.reward))}{" "}
        reward.
      </Caption>

      <View style={s.inputRow}>
        <Text style={s.rupee}>₹</Text>
        <TextInput
          value={value}
          onChangeText={setValue}
          keyboardType="numeric"
          placeholder="0"
          placeholderTextColor={colors.muted}
          style={s.input}
          accessibilityLabel="Amount you paid"
        />
      </View>

      {over ? (
        <Body style={s.over}>
          {rupees(spent - expected)} over the estimate — covered by the headroom held
          on this order, as long as it is within it.
        </Body>
      ) : null}

      <Button
        title="Confirm pickup"
        size="lg"
        loading={busy}
        disabled={!valid}
        onPress={() => onConfirm(spent)}
        style={{ marginTop: space.md }}
      />
    </Card>
  );
}

const s = StyleSheet.create({
  card: {
    marginTop: space.xl,
    borderWidth: 1,
    borderColor: colors.brand,
    backgroundColor: colors.brandSoft,
  },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    marginTop: space.md,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.lg,
    paddingHorizontal: space.md,
  },
  rupee: { fontSize: 20, fontFamily: font.bold, color: colors.ink },
  input: {
    flex: 1,
    paddingVertical: space.md,
    fontSize: 20,
    fontFamily: font.bold,
    color: colors.ink,
  },
  over: {
    marginTop: space.sm,
    color: colors.amberText,
    fontSize: 13,
  },
});
