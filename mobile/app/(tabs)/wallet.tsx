import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { RefreshControl, StyleSheet, Text, View } from "react-native";

import { type LedgerEntry, fetchWallet } from "../../src/api/wallet";
import { Icon, type IconName } from "../../src/components/icons";
import {
  Button,
  EmptyState,
  Eyebrow,
  Hero,
  Pill,
  Screen,
  SkeletonRow,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { notify } from "../../src/lib/dialog";
import { colors, font, radius, rupeesLong, shadow, space } from "../../src/theme";

/**
 * Every entry type the ledger can write, in the words a student would use.
 *
 * The ledger's own names are accounting terms, HOLD and CLAWBACK and
 * REIMBURSEMENT, and they are correct there. They are not what someone checking
 * why their balance moved wants to read, and a wallet that cannot explain a
 * debit is a wallet nobody trusts.
 */
const ENTRY: Record<string, { label: string; note: string; icon: IconName }> = {
  TOPUP: { label: "Money added", note: "You topped up your wallet", icon: "in" },
  HOLD: {
    label: "Held for an errand",
    note: "Ring fenced until you confirm",
    icon: "lock",
  },
  REFUND: {
    label: "Returned to you",
    note: "The errand did not go ahead",
    icon: "in",
  },
  REWARD: { label: "You earned this", note: "Runner fee for a completed errand", icon: "bike" },
  REIMBURSEMENT: {
    label: "Spending returned",
    note: "What you paid at the counter",
    icon: "receipt",
  },
  REVIEW_REFUND: {
    label: "Returned after review",
    note: "An admin reviewed a held amount",
    icon: "scale",
  },
  CLAWBACK: {
    label: "Taken back",
    note: "Reversed after a review went against it",
    icon: "out",
  },
};

function describe(entry: LedgerEntry) {
  return (
    ENTRY[entry.entry_type] ?? {
      label: entry.entry_type.replaceAll("_", " ").toLowerCase(),
      note: "",
      icon: "cash" as IconName,
    }
  );
}

/** Group entries by calendar day, so the list reads as a history. */
function byDay(entries: LedgerEntry[]) {
  const groups = new Map<string, LedgerEntry[]>();
  for (const e of entries) {
    const d = new Date(e.created_at);
    const key = d.toDateString();
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(e);
  }
  return [...groups.entries()];
}

function dayLabel(key: string) {
  const today = new Date().toDateString();
  const yesterday = new Date(Date.now() - 86400000).toDateString();
  if (key === today) return "Today";
  if (key === yesterday) return "Yesterday";
  return new Date(key).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function WalletScreen() {
  const { data, isLoading, isError, error, refetch, isRefetching } = useQuery({
    queryKey: ["wallet"],
    queryFn: fetchWallet,
  });

  const days = useMemo(() => byDay(data?.recent ?? []), [data?.recent]);

  const available = data?.balance ?? 0;
  const held = data?.held ?? 0;
  const total = available + held;
  // Guard the split bar against a zero total, which would otherwise divide by
  // nothing and render an empty track that looks like a loading state.
  const availablePct = total > 0 ? (available / total) * 100 : 100;

  return (
    <Screen
      scroll
      padded={false}
      edges={[]}
      bg={colors.bgSoft}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
      }
    >
      <Hero tone="deep" eyebrow="Your money" padBottom={74}>
        <View style={s.titleRow}>
          <Text style={s.walletTitle}>Wallet</Text>
          <Pill
            label="Escrow protected"
            icon="shield"
            bg="rgba(255,255,255,0.14)"
            color={colors.white}
            style={{ marginBottom: 6 }}
          />
        </View>
      </Hero>

      <View style={s.body}>
        {/* One card, one bar. Held is not a footnote on the balance: it is the
            other half of the answer to "where is my money", and the split bar
            says what share of the total is still locked before either number
            is read. */}
        <View style={[s.balanceCard, shadow.raised]}>
          <Text style={s.balanceLabel}>Total in wallet</Text>
          <View style={s.balanceRow}>
            <Text style={s.rupee}>₹</Text>
            <Text style={s.balance}>
              {isLoading ? "—" : Math.round(total).toLocaleString("en-IN")}
            </Text>
          </View>

          <View style={s.splitBar}>
            <View style={{ width: `${availablePct}%`, backgroundColor: colors.brand }} />
            <View style={{ width: `${100 - availablePct}%`, backgroundColor: colors.money }} />
          </View>

          <View style={s.partitions}>
            <View style={[s.partition, { backgroundColor: colors.bgSoft }]}>
              <View style={s.partitionHead}>
                <Icon name="cash" size={15} color={colors.brand} />
                <Text style={[s.partitionLabel, { color: colors.brand }]}>Available</Text>
              </View>
              <Text style={s.partitionAmount}>{isLoading ? "—" : rupeesLong(available)}</Text>
              <Text style={s.partitionNote}>Yours to spend now</Text>
            </View>

            <View style={[s.partition, { backgroundColor: colors.warnBg }]}>
              <View style={s.partitionHead}>
                <Icon name="lock" size={15} color={colors.warnText} />
                <Text style={[s.partitionLabel, { color: colors.warnText }]}>Held</Text>
              </View>
              <Text style={[s.partitionAmount, { color: colors.warnText }]}>
                {isLoading ? "—" : rupeesLong(held)}
              </Text>
              <Text style={[s.partitionNote, { color: colors.warnText }]}>
                {held > 0 ? "Locked on live orders" : "No orders in flight"}
              </Text>
            </View>
          </View>

          <View style={s.actions}>
            <View style={{ flex: 1 }}>
              <Button
                title="Add money"
                icon="in"
                onPress={() =>
                  notify(
                    "Not connected yet",
                    "Payments go through a licensed gateway, which isn't wired up yet.",
                  )
                }
              />
            </View>
            <View style={{ flex: 1 }}>
              <Button
                title="Withdraw"
                icon="out"
                variant="outline"
                onPress={() =>
                  notify(
                    "Not connected yet",
                    "Withdrawals need the same gateway, so this is on hold too.",
                  )
                }
              />
            </View>
          </View>
        </View>

        {isLoading ? (
          <View style={{ marginTop: space.lg, gap: space.sm }}>
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </View>
        ) : isError ? (
          <View style={{ marginTop: space.lg }}>
            <EmptyState
              icon="alert"
              title="Couldn't load your wallet"
              body={apiErrorMessage(error, "Check your connection and try again.")}
              action={<Button title="Try again" onPress={() => refetch()} />}
            />
          </View>
        ) : !data?.recent?.length ? (
          <View style={{ marginTop: space.lg }}>
            <EmptyState
              icon="cash"
              title="Nothing yet"
              body="Money you add, earn or spend will show up here with the reason."
            />
          </View>
        ) : (
          days.map(([day, entries], gi) => (
            <View key={day} style={{ marginTop: gi === 0 ? space.lg : space.xl }}>
              <View style={s.sectionHead}>
                {gi === 0 ? <Text style={s.sectionTitle}>Transactions</Text> : <View />}
                <Eyebrow>{dayLabel(day)}</Eyebrow>
              </View>

              <View style={s.list}>
                {entries.map((e, i) => {
                  const meta = describe(e);
                  const credit = e.direction === "CREDIT";
                  return (
                    <View key={e.id} style={[s.entry, i > 0 && s.entryDivider]}>
                      <View
                        style={[
                          s.entryIcon,
                          {
                            backgroundColor: credit
                              ? colors.creditBg
                              : e.entry_type === "HOLD"
                                ? colors.warnBg
                                : colors.bgSoft,
                          },
                        ]}
                      >
                        <Icon
                          name={meta.icon}
                          size={19}
                          color={
                            credit
                              ? colors.credit
                              : e.entry_type === "HOLD"
                                ? colors.warnText
                                : colors.muted
                          }
                        />
                      </View>

                      <View style={{ flex: 1, minWidth: 0 }}>
                        <Text numberOfLines={1} style={s.entryLabel}>
                          {meta.label}
                        </Text>
                        <Text numberOfLines={1} style={s.entryNote}>
                          {e.memo || meta.note}
                        </Text>
                      </View>

                      <View style={{ alignItems: "flex-end" }}>
                        {/* Sign, not colour alone: the direction has to be
                            readable without relying on hue. */}
                        <Text
                          style={[s.amount, { color: credit ? colors.credit : colors.ink }]}
                        >
                          {credit ? "+" : "−"}
                          {rupeesLong(e.amount)}
                        </Text>
                        <Text style={s.entryTime}>
                          {new Date(e.created_at).toLocaleTimeString(undefined, {
                            hour: "numeric",
                            minute: "2-digit",
                          })}
                        </Text>
                      </View>
                    </View>
                  );
                })}
              </View>
            </View>
          ))
        )}
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  titleRow: { flexDirection: "row", alignItems: "flex-end", gap: 10, marginTop: 8 },
  walletTitle: { color: colors.white, fontSize: 32, fontFamily: font.black, letterSpacing: -1 },

  // Pulled up so the card straddles the band, which is what makes the balance
  // read as sitting on top of the wallet rather than under a heading.
  body: { paddingHorizontal: 22, marginTop: -56 },

  balanceCard: {
    backgroundColor: colors.white,
    borderRadius: radius.big,
    borderWidth: 1,
    borderColor: colors.hairline,
    padding: space.xl,
  },
  balanceLabel: { color: colors.muted, fontSize: 12, fontFamily: font.semi },
  balanceRow: { flexDirection: "row", alignItems: "baseline", gap: 4, marginTop: 4 },
  rupee: { color: colors.mutedCool, fontSize: 26, fontFamily: font.bold, letterSpacing: -0.6 },
  balance: { color: colors.ink, fontSize: 42, fontFamily: font.black, letterSpacing: -1.6 },

  splitBar: {
    flexDirection: "row",
    gap: 6,
    marginTop: space.lg,
    height: 8,
    borderRadius: 4,
    overflow: "hidden",
    backgroundColor: colors.hairline,
  },

  partitions: { flexDirection: "row", gap: 12, marginTop: 14 },
  partition: { flex: 1, borderRadius: radius.lg, padding: 13 },
  partitionHead: { flexDirection: "row", alignItems: "center", gap: 6 },
  partitionLabel: { fontSize: 11.5, fontFamily: font.bold },
  partitionAmount: {
    color: colors.ink,
    fontSize: 22,
    fontFamily: font.black,
    letterSpacing: -0.6,
    marginTop: 4,
  },
  partitionNote: { color: colors.muted, fontSize: 11, fontFamily: font.regular, marginTop: 1 },

  actions: { flexDirection: "row", gap: 10, marginTop: space.lg },

  sectionHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 12,
  },
  sectionTitle: { color: colors.ink, fontSize: 16, fontFamily: font.black, letterSpacing: -0.3 },

  list: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.xxl,
    overflow: "hidden",
  },
  entry: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 15,
    paddingVertical: 12,
  },
  entryDivider: { borderTopWidth: 1, borderTopColor: colors.hairlineSoft },
  entryIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    alignItems: "center",
    justifyContent: "center",
  },
  entryLabel: { color: colors.ink, fontSize: 13.5, fontFamily: font.semi },
  entryNote: { color: colors.muted, fontSize: 11.5, fontFamily: font.regular, marginTop: 1 },
  amount: { fontSize: 14, fontFamily: font.bold },
  entryTime: { color: colors.mutedCool, fontSize: 10, fontFamily: font.regular },
});
