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

  // Once the runner declares what they paid, that is the number settlement
  // reimburses - so it is the number both sides should be shown. Before then
  // the estimate is the honest answer, and it is labelled as one.
  const declared = errand.amount_spent != null ? Number(errand.amount_spent) : null;
  const spend = declared ?? items + collect;

  const settled = errand.status === "COMPLETED";

  if (isRequester) {
    const total = spend + reward;
    return (
      <Card raised style={{ marginTop: space.lg }}>
        <Row justify="space-between" style={{ marginBottom: space.md }}>
          <Body style={{ fontFamily: font.black }}>Payment</Body>
          <Caption style={{ color: settled ? colors.greenText : colors.amberText }}>
            {settled ? "Settled" : "Due on handover"}
          </Caption>
        </Row>

        <View style={{ gap: space.md }}>
          {declared != null ? (
            <Line
              label="What your runner paid"
              value={rupees(declared)}
              hint="Declared at pickup"
            />
          ) : (
            <>
              {items > 0 ? (
                <Line
                  label="Items"
                  value={rupees(items)}
                  hint="What the runner bought for you"
                />
              ) : null}
              {collect > 0 ? (
                <Line
                  label="Cash paid at pickup"
                  value={rupees(collect)}
                  hint="Your runner paid this out of pocket"
                />
              ) : null}
            </>
          )}
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

  // Runner's side — exactly what the ledger will credit. Reimbursement follows
  // the declaration, not collect_amount: a shopping order carries its spend as
  // priced items, so quoting collect alone promised ₹0 back on the exact
  // errands where the runner had fronted the most.
  const payout = reward + spend;
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
        {spend > 0 ? (
          <Line
            label="Reimbursement"
            value={rupees(spend)}
            hint={
              declared != null
                ? "What you declared paying at pickup, back"
                : "Estimated — confirmed when you mark it picked up"
            }
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
