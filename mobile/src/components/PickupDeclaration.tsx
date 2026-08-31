import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import type { Errand } from "../api/errands";
import { fetchEscrow } from "../api/wallet";
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

  // The ceiling comes from the hold itself rather than being recomputed here.
  // It is the exact figure settlement measures against, and a client that
  // does its own arithmetic will eventually disagree with it.
  const { data: escrow } = useQuery({
    queryKey: ["escrow", errand.id],
    queryFn: () => fetchEscrow(errand.id),
  });

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

  // Past the hold, nobody gets paid on delivery - the requester never
  // committed that much, so it goes to an admin instead. Saying so here beats
  // letting the runner find out when their payout does not arrive.
  const ceiling = escrow ? Number(escrow.amount) : null;
  const owed = spent + Number(errand.reward || 0);
  const pastCeiling = valid && ceiling != null && owed > ceiling;

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

      {pastCeiling ? (
        <View style={s.blocked}>
          <Body style={s.blockedText}>
            This is more than the {rupees(ceiling!)} held for this order. Paying you{" "}
            {rupees(owed)} would charge your requester more than they agreed to lock,
            so nothing will be paid out on delivery — an admin reviews it first.
          </Body>
          <Caption style={{ color: colors.redText, marginTop: space.xs }}>
            Report it anyway if it is what you really paid. Do not inflate it.
          </Caption>
        </View>
      ) : over ? (
        <Body style={s.over}>
          {rupees(spent - expected)} over the estimate — covered by the headroom held
          on this order.
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
  blocked: {
    marginTop: space.sm,
    padding: space.md,
    borderRadius: radius.lg,
    backgroundColor: colors.redBg,
    borderWidth: 1,
    borderColor: colors.redBorder,
  },
  blockedText: { color: colors.redText, fontSize: 13 },
});
