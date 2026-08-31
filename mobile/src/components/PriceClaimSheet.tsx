import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import type { Errand } from "../api/errands";
import { type ClaimLine, type ClaimResult, submitClaims } from "../api/fraud";
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

  const priced = lines.filter((l) => l.name.trim() && l.unit_price > 0);
  const itemsTotal = priced.reduce((sum, l) => sum + l.unit_price * l.quantity, 0);
  const customerPays = itemsTotal + errand.reward;
  const complete = priced.length === lines.length && lines.length > 0;

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
      <Heading>What did you pay?</Heading>
      <Caption style={{ marginTop: space.xs }}>
        Enter the price per item as printed at the counter. We add it up and the
        customer pays that plus your fee.
      </Caption>

      <View style={{ gap: space.md, marginTop: space.lg }}>
        {lines.map((line, i) => (
          <View key={`${line.name}-${i}`}>
            <Row gap={space.md}>
              <View style={{ flex: 1 }}>
                <Body numberOfLines={1} style={{ fontFamily: font.semi }}>
                  {line.name}
                </Body>
                <Caption>
                  {/* Quantity comes from the order, not the runner. */}
                  {line.quantity} × unit price
                </Caption>
              </View>

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
          <Body style={{ fontFamily: font.bold }}>Customer pays</Body>
          <Text style={s.grand}>{rupees(customerPays)}</Text>
        </Row>
      </View>

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
  priceBox: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.lg,
    paddingHorizontal: space.sm,
    minWidth: 88,
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
  lineTotal: { minWidth: 62, alignItems: "flex-end" },
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

  note: {
    marginTop: space.md,
    padding: space.md,
    backgroundColor: colors.amberBg,
    borderRadius: radius.lg,
  },
});
