import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import type { Errand } from "../api/errands";
import { type ClaimLine, type ClaimResult, submitClaims } from "../api/fraud";
import { fetchEscrow } from "../api/wallet";
import { apiErrorMessage } from "../lib/api";
import { colors, font, radius, rupees, space } from "../theme";
import { Body, Button, Caption, Card, ErrorNote, Heading, Row } from "./ui";

/**
 * What the runner actually paid, reported at the counter.
 *
 * Shown BEFORE delivery on purpose: a runner who is about to be paid less than
 * they asked for should learn it here, standing at the till with the receipt
 * they never got, rather than finding a smaller number in their wallet later
 * with no explanation attached.
 *
 * Lines are prefilled from the customer's own list, including quantity. The
 * runner should never retype "chicken puff" and "2" — the requester already
 * said that. They enter one number per line: the unit price. Getting quantity
 * from the order rather than from the runner also removes an obvious way to
 * inflate a total without touching a unit price that would be checked.
 */
export function PriceClaimSheet({
  errand,
  onSubmitted,
}: {
  errand: Errand;
  onSubmitted?: () => void;
}) {
  // Unavailable items were never bought, so they are not offered for pricing.
  const [lines, setLines] = useState<ClaimLine[]>(() =>
    errand.items
      .filter((i) => i.is_available)
      .map((i) => ({ name: i.name_snapshot, unit_price: 0, quantity: i.quantity })),
  );
  const [result, setResult] = useState<ClaimResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function update(index: number, patch: Partial<ClaimLine>) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  }

  const { data: escrow } = useQuery({
    queryKey: ["escrow", errand.id],
    queryFn: () => fetchEscrow(errand.id),
  });

  const priced = lines.filter((l) => l.name.trim() && l.unit_price > 0);
  const itemsTotal = priced.reduce((sum, l) => sum + l.unit_price * l.quantity, 0);
  const customerPays = itemsTotal + errand.reward;
  const complete = priced.length === lines.length && lines.length > 0;

  // Past what the requester locked, nobody is paid on delivery: the money was
  // never committed, so it goes to an admin instead. Saying so here beats
  // letting the runner discover it when their payout does not arrive.
  const ceiling = escrow ? Number(escrow.amount) : null;
  const overCeiling = ceiling != null && customerPays > ceiling;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await submitClaims(errand.id, priced);
      setResult(res);
      onSubmitted?.();
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't submit those prices."));
    } finally {
      setBusy(false);
    }
  }

  if (result) return <ClaimOutcome result={result} reward={errand.reward} />;

  return (
    <Card style={{ marginTop: space.lg }}>
      <Heading>Report what you paid</Heading>
      <Caption style={{ marginTop: space.xs }}>
        Enter the price per item as printed at the counter. We add it up, and it
        is reimbursed to your wallet with your fee when the customer confirms.
      </Caption>

      <View style={{ gap: space.md, marginTop: space.lg }}>
        {lines.map((line, i) => (
          <View key={`${line.name}-${i}`}>
            <Row gap={space.sm} align="center">
              {/* One sentence, read left to right: "2 x Chicken Puff at [ ]".
                  The quantity comes from the customer's order, not from the
                  runner, so a total cannot be inflated without touching a
                  unit price that gets checked. */}
              <Body style={s.lineLabel} numberOfLines={2}>
                <Text style={{ fontFamily: font.bold }}>{line.quantity}× </Text>
                <Text style={{ fontFamily: font.semi }}>{line.name}</Text>
                <Text style={{ color: colors.muted }}> at</Text>
              </Body>

              <View style={s.priceBox}>
                <Text style={s.rupee}>₹</Text>
                <TextInput
                  value={line.unit_price ? String(line.unit_price) : ""}
                  onChangeText={(v) => {
                    const n = Number(v.replace(/[^0-9.]/g, ""));
                    update(i, { unit_price: Number.isFinite(n) ? n : 0 });
                  }}
                  keyboardType="decimal-pad"
                  placeholder="0"
                  placeholderTextColor={colors.muted}
                  style={s.priceInput}
                  maxLength={7}
                />
              </View>

              <View style={s.lineTotal}>
                <Text style={s.lineTotalText}>
                  {line.unit_price > 0 ? rupees(line.unit_price * line.quantity) : "—"}
                </Text>
              </View>
            </Row>
          </View>
        ))}
      </View>

      {/* The arithmetic, shown rather than implied — the runner is about to be
          held to this number. */}
      <View style={s.totals}>
        <Row justify="space-between">
          <Caption>Items</Caption>
          <Body style={{ fontFamily: font.semi }}>{rupees(itemsTotal)}</Body>
        </Row>
        <Row justify="space-between" style={{ marginTop: 4 }}>
          <Caption>Your fee</Caption>
          <Body style={{ fontFamily: font.semi }}>{rupees(errand.reward)}</Body>
        </Row>
        <Row justify="space-between" style={s.grandRow}>
          <Body style={{ fontFamily: font.bold }}>You receive</Body>
          <Text style={s.grand}>{rupees(customerPays)}</Text>
        </Row>
      </View>

      {overCeiling ? (
        <View style={s.warn}>
          <Body style={{ color: colors.redText, fontSize: 13 }}>
            That comes to {rupees(customerPays)}, more than the {rupees(ceiling!)}
            {" "}held for this errand.
          </Body>
          <Caption style={{ color: colors.redText, marginTop: space.xs }}>
            You can still report it if it is what you really paid — but nothing
            is paid out on delivery. An admin reviews the difference first.
          </Caption>
        </View>
      ) : null}

      {error ? (
        <View style={{ marginTop: space.md }}>
          <ErrorNote>{error}</ErrorNote>
        </View>
      ) : null}

      <Button
        title="Submit prices"
        size="lg"
        style={{ marginTop: space.lg }}
        loading={busy}
        disabled={!complete}
        onPress={submit}
      />
      {!complete ? (
        <Caption style={{ marginTop: space.sm, textAlign: "center" }}>
          Enter a price for every item to continue.
        </Caption>
      ) : null}
    </Card>
  );
}

/** The verdict, per line, with any withheld amount stated plainly. */
function ClaimOutcome({ result, reward }: { result: ClaimResult; reward: number }) {
  const held = result.withheld > 0;

  return (
    <Card style={{ marginTop: space.lg }}>
      <Heading>{held ? "Some of this is on hold" : "Prices recorded"}</Heading>

      <View style={{ gap: space.sm, marginTop: space.md }}>
        {result.claims.map((c) => {
          const tone =
            c.verdict === "FLAGGED"
              ? { bg: colors.redBg, fg: colors.redText, label: "Above reference" }
              : c.verdict === "ELEVATED"
                ? { bg: colors.amberBg, fg: colors.amberText, label: "A little high" }
                : c.verdict === "NO_REFERENCE"
                  ? { bg: colors.bgSoft, fg: colors.muted, label: "No reference yet" }
                  : { bg: colors.greenBg, fg: colors.greenText, label: "Normal" };
          return (
            <Row key={c.id} justify="space-between" gap={space.md}>
              <View style={{ flex: 1 }}>
                <Body numberOfLines={1}>{c.raw_name}</Body>
                <Caption>
                  {c.quantity} × {rupees(c.claimed_unit_price)}
                  {c.reference_snapshot != null
                    ? ` · reference ${rupees(c.reference_snapshot)}`
                    : ""}
                </Caption>
              </View>
              <View style={[s.verdict, { backgroundColor: tone.bg }]}>
                <Text style={[s.verdictText, { color: tone.fg }]}>{tone.label}</Text>
              </View>
            </Row>
          );
        })}
      </View>

      <View style={s.totals}>
        <Row justify="space-between">
          <Caption>You reported</Caption>
          <Body style={{ fontFamily: font.semi }}>{rupees(result.total_claimed)}</Body>
        </Row>
        <Row justify="space-between" style={{ marginTop: 4 }}>
          <Caption>Reimbursed now</Caption>
          <Body style={{ fontFamily: font.semi }}>{rupees(result.total_eligible)}</Body>
        </Row>
        {held ? (
          <Row justify="space-between" style={{ marginTop: 4 }}>
            <Caption style={{ color: colors.amberText }}>On hold for review</Caption>
            <Body style={{ fontFamily: font.bold, color: colors.amberText }}>
              {rupees(result.withheld)}
            </Body>
          </Row>
        ) : null}
        <Row justify="space-between" style={s.grandRow}>
          <Body style={{ fontFamily: font.bold }}>Your fee</Body>
          <Text style={s.grand}>{rupees(reward)}</Text>
        </Row>
      </View>

      {result.message ? (
        <View style={s.note}>
          <Caption style={{ color: colors.amberText }}>{result.message}</Caption>
        </View>
      ) : null}
    </Card>
  );
}

const s = StyleSheet.create({
  lineLabel: { flex: 1, flexShrink: 1 },
  priceBox: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.lg,
    paddingHorizontal: space.sm,
    // A fixed width, not a minimum. The input inside is flex:1, and against a
    // merely-minimum width that grows until the item name has one character
    // per line - which is exactly what it did.
    width: 96,
    flexGrow: 0,
    flexShrink: 0,
    backgroundColor: colors.white,
  },
  rupee: { color: colors.muted, fontSize: font.body, fontFamily: font.semi },
  priceInput: {
    flex: 1,
    paddingVertical: 9,
    paddingHorizontal: 4,
    color: colors.ink,
    fontSize: font.body,
    fontFamily: font.bold,
  },
  lineTotal: { width: 62, flexGrow: 0, flexShrink: 0, alignItems: "flex-end" },
  lineTotalText: { color: colors.ink, fontSize: font.body, fontFamily: font.bold },

  totals: {
    marginTop: space.lg,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: colors.line,
  },
  grandRow: {
    marginTop: space.sm,
    paddingTop: space.sm,
    borderTopWidth: 1,
    borderTopColor: colors.line,
  },
  grand: { color: colors.brandDark, fontSize: font.h3, fontFamily: font.black },

  verdict: {
    paddingHorizontal: space.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  verdictText: { fontSize: font.tiny, fontFamily: font.bold },

  warn: {
    marginTop: space.md,
    padding: space.md,
    borderRadius: radius.lg,
    backgroundColor: colors.redBg,
    borderWidth: 1,
    borderColor: colors.redBorder,
  },
  note: {
    marginTop: space.md,
    padding: space.md,
    backgroundColor: colors.amberBg,
    borderRadius: radius.lg,
  },
});
