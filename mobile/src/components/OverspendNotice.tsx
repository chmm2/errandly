import { useQuery } from "@tanstack/react-query";
import { StyleSheet, View } from "react-native";

import type { Errand } from "../api/errands";
import { fetchEscrow } from "../api/wallet";
import { colors, radius, rupees, space } from "../theme";
import { Body, Caption, Heading } from "./ui";

/**
 * Told to the requester before they confirm: this bill is bigger than the hold.
 *
 * Confirming still goes through — the delivery happened and the runner should
 * not be stuck waiting on a dispute about money. What changes is that nothing
 * settles: the amount stays in the held partition and an admin decides. Saying
 * it here means the requester is not surprised later by money that neither
 * came back nor went anywhere.
 */
export function OverspendNotice({ errand }: { errand: Errand }) {
  const { data: escrow } = useQuery({
    queryKey: ["escrow", errand.id],
    queryFn: () => fetchEscrow(errand.id),
  });

  if (errand.amount_spent == null || !escrow) return null;

  const ceiling = Number(escrow.amount);
  const owed = Number(errand.amount_spent) + Number(errand.reward || 0);
  if (owed <= ceiling) return null;

  return (
    <View style={s.box}>
      <Heading style={{ fontSize: 15, color: colors.redText }}>
        This bill is more than you locked
      </Heading>
      <Body style={s.text}>
        Your runner reported paying {rupees(Number(errand.amount_spent))}, which with
        their {rupees(Number(errand.reward))} reward comes to {rupees(owed)}. You
        locked {rupees(ceiling)}.
      </Body>
      <Caption style={{ color: colors.redText, marginTop: space.sm }}>
        You will not be charged the extra {rupees(owed - ceiling)}. Confirming leaves
        your money held and sends the difference to an admin to settle.
      </Caption>
    </View>
  );
}

const s = StyleSheet.create({
  box: {
    marginTop: space.lg,
    padding: space.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.redBg,
    borderWidth: 1,
    borderColor: colors.redBorder,
  },
  text: { color: colors.redText, fontSize: 13, marginTop: space.xs },
});
