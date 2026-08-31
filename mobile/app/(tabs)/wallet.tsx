import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { RefreshControl, StyleSheet, Text, View } from "react-native";

import { type LedgerEntry, fetchWallet } from "../../src/api/wallet";
import {
  Body,
  Button,
  Caption,
  Card,
  EmptyState,
  Hero,
  Loading,
  Row,
  Screen,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { notify } from "../../src/lib/dialog";
import { colors, font, radius, rupees, space } from "../../src/theme";

/**
 * Every entry type the ledger can write, in the words a student would use.
 *
 * The ledger's own names are accounting terms — HOLD, CLAWBACK, REIMBURSEMENT —
 * and they are correct there. They are not what someone checking why their
 * balance moved wants to read, and a wallet that cannot explain a debit is a
 * wallet nobody trusts.
 */
const ENTRY: Record<string, { label: string; note: string; emoji: string }> = {
  TOPUP: { label: "Money added", note: "You topped up your wallet", emoji: "＋" },
  HOLD: {
    label: "Held for an errand",
    note: "Ring-fenced until the errand is confirmed",
    emoji: "🔒",
  },
  REFUND: {
    label: "Returned to you",
    note: "The errand did not go ahead",
    emoji: "↩",
  },
  REWARD: { label: "You earned this", note: "Runner fee for a completed errand", emoji: "🛵" },
  REIMBURSEMENT: {
    label: "Spending returned",
    note: "What you paid at the counter",
    emoji: "🧾",
  },
  REVIEW_REFUND: {
    label: "Returned after review",
    note: "An admin reviewed a held amount",
    emoji: "⚖️",
  },
  CLAWBACK: {
    label: "Taken back",
    note: "Reversed after a review went against it",
    emoji: "↖",
  },
};

function describe(entry: LedgerEntry) {
  return (
    ENTRY[entry.entry_type] ?? {
      label: entry.entry_type.replaceAll("_", " ").toLowerCase(),
      note: "",
      emoji: "•",
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

  return (
    <Screen
      scroll
      padded={false}
      refreshControl={
        <RefreshControl
          refreshing={isRefetching}
          onRefresh={refetch}
          tintColor={colors.brand}
        />
      }
    >
      <Hero eyebrow="Your money" title="Wallet" />

      <View style={{ paddingHorizontal: space.lg }}>
        {/* Balance */}
        <Card raised style={s.balanceCard}>
          <Caption style={{ color: colors.muted }}>Available to spend</Caption>
          <Text style={s.balance}>
            {isLoading ? "—" : rupees(data?.balance ?? 0)}
          </Text>

          {/* Escrow is money that has already left the balance. Showing it
              explains where it went, rather than leaving a hole to guess at. */}
          {(data?.held ?? 0) > 0 ? (
            <View style={s.held}>
              <Row gap={space.sm}>
                <Text style={{ fontSize: 13 }}>🔒</Text>
                <Caption style={{ flex: 1, color: colors.amberText }}>
                  {rupees(data!.held)} held against errands in flight — released
                  when they are confirmed
                </Caption>
              </Row>
            </View>
          ) : null}

          <Row gap={space.sm} style={{ marginTop: space.lg }}>
            <View style={{ flex: 1 }}>
              <Button
                title="Add money"
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
                title="Retrieve money"
                variant="outline"
                onPress={() =>
                  notify(
                    "Not connected yet",
                    "Withdrawals need the same gateway, so this is on hold too.",
                  )
                }
              />
            </View>
          </Row>
        </Card>

        {/* History */}
        <Row justify="space-between" style={{ marginTop: space.xxl }}>
          <Body style={{ fontFamily: font.bold }}>Transactions</Body>
          {data?.recent?.length ? (
            <Caption>{data.recent.length} most recent</Caption>
          ) : null}
        </Row>

        {isLoading ? (
          <Loading label="Loading your wallet…" />
        ) : isError ? (
          <EmptyState
            emoji="😕"
            title="Couldn't load your wallet"
            body={apiErrorMessage(error, "Check your connection and try again.")}
            action={<Button title="Try again" onPress={() => refetch()} />}
          />
        ) : !data?.recent?.length ? (
          <EmptyState
            emoji="🪙"
            title="Nothing yet"
            body="Money you add, earn or spend will show up here with the reason."
          />
        ) : (
          <View style={{ marginTop: space.md }}>
            {days.map(([day, entries]) => (
              <View key={day} style={{ marginBottom: space.lg }}>
                <Caption style={s.dayHeading}>{dayLabel(day)}</Caption>
                <Card style={{ padding: 0 }}>
                  {entries.map((e, i) => {
                    const meta = describe(e);
                    const credit = e.direction === "CREDIT";
                    return (
                      <View
                        key={e.id}
                        style={[s.entry, i > 0 && s.entryDivider]}
                      >
                        <View
                          style={[
                            s.icon,
                            { backgroundColor: credit ? colors.greenBg : colors.bgSoft },
                          ]}
                        >
                          <Text style={{ fontSize: 15 }}>{meta.emoji}</Text>
                        </View>

                        <View style={{ flex: 1, minWidth: 0 }}>
                          <Body numberOfLines={1} style={{ fontFamily: font.semi }}>
                            {meta.label}
                          </Body>
                          <Caption numberOfLines={1}>
                            {e.memo || meta.note}
                          </Caption>
                        </View>

                        <View style={{ alignItems: "flex-end" }}>
                          {/* Sign, not colour alone — the direction has to be
                              readable without relying on hue. */}
                          <Text
                            style={[
                              s.amount,
                              { color: credit ? colors.greenText : colors.ink },
                            ]}
                          >
                            {credit ? "+" : "−"}
                            {rupees(e.amount)}
                          </Text>
                          <Caption style={{ fontSize: 10 }}>
                            {new Date(e.created_at).toLocaleTimeString(undefined, {
                              hour: "numeric",
                              minute: "2-digit",
                            })}
                          </Caption>
                        </View>
                      </View>
                    );
                  })}
                </Card>
              </View>
            ))}
          </View>
        )}
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  balanceCard: { marginTop: space.xl, alignItems: "stretch" },
  balance: {
    color: colors.ink,
    fontSize: 40,
    fontFamily: font.black,
    letterSpacing: -1,
    marginTop: 2,
  },
  held: {
    marginTop: space.md,
    padding: space.md,
    backgroundColor: colors.amberBg,
    borderRadius: radius.lg,
  },

  dayHeading: {
    fontFamily: font.bold,
    color: colors.muted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
    fontSize: 10,
    marginBottom: space.sm,
  },
  entry: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  entryDivider: { borderTopWidth: 1, borderTopColor: colors.line },
  icon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
  },
  amount: { fontSize: font.body, fontFamily: font.bold },
});
