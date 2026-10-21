import { StyleSheet, Text, View } from "react-native";

import type { Errand } from "../api/errands";
import { colors, font, radius, rupees, space } from "../theme";
import { Icon, type IconName } from "./icons";

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
    <View style={s.line}>
      <View style={{ flex: 1 }}>
        <Text style={[s.label, strong && s.labelStrong]}>{label}</Text>
        {hint ? <Text style={s.hint}>{hint}</Text> : null}
      </View>
      <Text style={[s.amount, strong && s.amountStrong]}>{value}</Text>
    </View>
  );
}

/** Card header: an icon, what the money is, and where it stands. */
function Head({
  icon,
  title,
  state,
  done,
}: {
  icon: IconName;
  title: string;
  state: string;
  done: boolean;
}) {
  return (
    <View style={s.head}>
      <Icon name={icon} size={17} color={colors.brand} />
      <Text style={s.title}>{title}</Text>
      <Text style={[s.state, { color: done ? colors.credit : colors.warnText }]}>{state}</Text>
    </View>
  );
}

/**
 * The money, from whichever side you're on.
 *
 * Requester sees what they owe; runner sees what they're due. The runner's
 * figures mirror the settlement consumer exactly, reward plus any cash they
 * fronted, so the app never promises a payout the ledger won't make.
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
  // reimburses, so it is the number both sides should be shown. Before then
  // the estimate is the honest answer, and it is labelled as one.
  const declared = errand.amount_spent != null ? Number(errand.amount_spent) : null;
  const spend = declared ?? items + collect;

  const settled = errand.status === "COMPLETED";

  if (isRequester) {
    const total = spend + reward;
    return (
      <View style={s.card}>
        <Head
          icon="lock"
          title="Held in escrow"
          state={settled ? "Settled" : "Due on handover"}
          done={settled}
        />

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

        <View style={s.rule} />
        <Line label="Total for this errand" value={rupees(total)} strong />
      </View>
    );
  }

  // Runner's side: exactly what the ledger will credit. Reimbursement follows
  // the declaration, not collect_amount: a shopping order carries its spend as
  // priced items, so quoting collect alone promised ₹0 back on the exact
  // errands where the runner had fronted the most.
  const payout = reward + spend;
  return (
    <View style={s.card}>
      <Head
        icon="cash"
        title="Your payout"
        state={settled ? "Credited" : "On confirmation"}
        done={settled}
      />

      <View style={{ gap: space.md }}>
        <Line label="Reward" value={rupees(reward)} hint="For making the trip" />
        {spend > 0 ? (
          <Line
            label="Reimbursement"
            value={rupees(spend)}
            hint={
              declared != null
                ? "What you declared paying at pickup, back"
                : "Estimated, confirmed when you mark it picked up"
            }
          />
        ) : null}
      </View>

      <View style={s.rule} />
      <Line label="You receive" value={rupees(payout)} strong />
      <Text style={[s.hint, { marginTop: space.sm }]}>
        Credited to your balance once the customer confirms handover.
      </Text>
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    marginTop: 12,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.xxl,
    padding: 14,
  },
  head: { flexDirection: "row", alignItems: "center", gap: 9, marginBottom: 12 },
  title: { flex: 1, color: colors.ink, fontSize: 13, fontFamily: font.bold },
  state: { fontSize: 11, fontFamily: font.bold },

  line: { flexDirection: "row", alignItems: "flex-start", gap: space.md, marginTop: 8 },
  label: { color: colors.inkSoft, fontSize: 12.5, fontFamily: font.regular },
  labelStrong: { color: colors.ink, fontSize: 13, fontFamily: font.bold },
  hint: { color: colors.mutedCool, fontSize: 11, fontFamily: font.regular, marginTop: 1 },
  amount: {
    color: colors.inkSoft,
    fontSize: 12.5,
    fontFamily: font.semi,
    fontVariant: ["tabular-nums"],
  },
  amountStrong: { color: colors.ink, fontSize: 15, fontFamily: font.black },
  rule: {
    marginTop: 12,
    borderTopWidth: 1,
    borderStyle: "dashed",
    borderTopColor: colors.line,
  },
});
