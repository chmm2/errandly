import { StyleSheet, Text, View } from "react-native";

import type { Errand } from "../api/errands";
import { colors, font, rupees, space } from "../theme";
import { Body, Caption, Card, Divider, Row } from "./ui";

function Line({
  label,
  value,
  hint,
  strong = false,
}: {
  label: string;
  value: string;
  hint?: string;
  strong?: boolean;
}) {
  return (
    <Row justify="space-between" align="flex-start" gap={space.md}>
      <View style={{ flex: 1 }}>
        <Body style={strong ? { fontFamily: font.bold } : undefined}>{label}</Body>
        {hint ? <Caption style={{ marginTop: 1 }}>{hint}</Caption> : null}
      </View>
      <Text style={[s.amount, strong && s.amountStrong]}>{value}</Text>
    </Row>
  );
}

/**
 * The money, from whichever side you're on.
 *
 * Requester sees what they owe; runner sees what they're due. The runner's
 * figures mirror the settlement consumer exactly — reward plus any cash they
 * fronted — so the app never promises a payout the ledger won't make.
 */
export function PaymentSummary({
  errand,
  isRequester,
}: {
  errand: Errand;
  isRequester: boolean;
}) {
  const items = Number(errand.items_total) || 0;
  const collect = Number(errand.collect_amount) || 0;
  const reward = Number(errand.reward) || 0;

  const settled = errand.status === "COMPLETED";

  if (isRequester) {
    const total = items + collect + reward;
    return (
      <Card raised style={{ marginTop: space.lg }}>
        <Row justify="space-between" style={{ marginBottom: space.md }}>
          <Body style={{ fontFamily: font.black }}>Payment</Body>
          <Caption style={{ color: settled ? colors.greenText : colors.amberText }}>
            {settled ? "Settled" : "Due on handover"}
          </Caption>
        </Row>

        <View style={{ gap: space.md }}>
          {items > 0 ? (
            <Line label="Items" value={rupees(items)} hint="What the runner bought for you" />
          ) : null}
          {collect > 0 ? (
            <Line
              label="Cash paid at pickup"
              value={rupees(collect)}
              hint="Your runner paid this out of pocket"
            />
          ) : null}
          <Line label="Runner reward" value={rupees(reward)} />
        </View>

        <Divider style={{ marginVertical: space.lg }} />
        <Line label="Total to pay your runner" value={rupees(total)} strong />
        <Caption style={{ marginTop: space.sm }}>
          Hand this over in cash when your errand arrives.
        </Caption>
      </Card>
    );
  }

  // Runner's side — exactly what the ledger will credit.
  const payout = reward + collect;
  return (
    <Card raised style={{ marginTop: space.lg }}>
      <Row justify="space-between" style={{ marginBottom: space.md }}>
        <Body style={{ fontFamily: font.black }}>Your payout</Body>
        <Caption style={{ color: settled ? colors.greenText : colors.amberText }}>
          {settled ? "Credited" : "On confirmation"}
        </Caption>
      </Row>

      <View style={{ gap: space.md }}>
        <Line label="Reward" value={rupees(reward)} hint="For making the trip" />
        {collect > 0 ? (
          <Line
            label="Reimbursement"
            value={rupees(collect)}
            hint="The cash you paid at pickup, back"
          />
        ) : null}
      </View>

      <Divider style={{ marginVertical: space.lg }} />
      <Line label="You receive" value={rupees(payout)} strong />

      {items > 0 ? (
        <View style={s.collectNote}>
          <Caption style={{ color: colors.amberText }}>
            Collect {rupees(items)} for the items directly from the customer at handover — that
            part isn't settled through the app.
          </Caption>
        </View>
      ) : (
        <Caption style={{ marginTop: space.sm }}>
          Credited to your balance once the customer confirms handover.
        </Caption>
      )}
    </Card>
  );
}

const s = StyleSheet.create({
  amount: {
    color: colors.ink,
    fontSize: font.body,
    fontFamily: font.semi,
    fontVariant: ["tabular-nums"],
  },
  amountStrong: { color: colors.brand, fontSize: font.h3, fontFamily: font.black },
  collectNote: {
    marginTop: space.md,
    backgroundColor: colors.amberBg,
    borderRadius: 10,
    padding: space.md,
  },
});
