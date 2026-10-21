import { type UseQueryResult, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import {
  type Friend,
  type PendingRequest,
  type Relationship,
  type SearchResult,
  fetchFriends,
  fetchRequests,
  respondToRequest,
  searchStudents,
  sendRequest,
  unfriend,
} from "../../src/api/social";
import { Icon } from "../../src/components/icons";
import {
  Avatar,
  Button,
  EmptyState,
  Field,
  Hero,
  Screen,
  SkeletonRow,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { confirm, notify } from "../../src/lib/dialog";
import { colors, font, radius, shadow, space, timeAgo } from "../../src/theme";

type Tab = "friends" | "requests" | "find";

export default function Connects() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("friends");

  const friends = useQuery({ queryKey: ["friends"], queryFn: fetchFriends });
  const requests = useQuery({ queryKey: ["friend-requests"], queryFn: fetchRequests });

  const pendingCount = requests.data?.length ?? 0;
  const friendCount = friends.data?.length ?? 0;

  function refresh() {
    qc.invalidateQueries({ queryKey: ["friends"] });
    qc.invalidateQueries({ queryKey: ["friend-requests"] });
  }

  const refreshing = friends.isRefetching || requests.isRefetching;

  return (
    // padded={false} plus an inner padded View, matching every other tab: the
    // Hero has to run full bleed or its band stops short of the screen edges.
    <Screen
      scroll
      padded={false}
      edges={[]}
      bg={colors.bgSoft}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.brand} />
      }
    >
      <Hero
        eyebrow="Your circle"
        title="Connects"
        subtitle="Errands reach friends first, then friends of friends."
      />

      <View style={s.body}>
        <View style={s.tabs}>
          <TabChip
            label="Friends"
            count={friendCount}
            active={tab === "friends"}
            onPress={() => setTab("friends")}
          />
          <TabChip
            label="Requests"
            count={pendingCount}
            active={tab === "requests"}
            highlight={pendingCount > 0}
            onPress={() => setTab("requests")}
          />
          <TabChip
            label="Find"
            icon
            active={tab === "find"}
            onPress={() => setTab("find")}
          />
        </View>

        {/* Reach is the whole point of the tab: how many people an errand can
            actually get to before it falls back to strangers. */}
        <View style={s.reach}>
          <View style={s.reachHead}>
            <Icon name="connects" size={17} color={colors.brand} />
            <Text style={s.reachTitle}>Your reach right now</Text>
          </View>
          <View style={s.reachRow}>
            <View>
              <Text style={s.reachValue}>{friendCount}</Text>
              <Text style={s.reachLabel}>friend{friendCount === 1 ? "" : "s"}</Text>
            </View>
            {pendingCount > 0 ? (
              <>
                <View style={s.reachRule} />
                <View>
                  <Text style={[s.reachValue, { color: colors.brand }]}>{pendingCount}</Text>
                  <Text style={s.reachLabel}>waiting on you</Text>
                </View>
              </>
            ) : null}
            <AvatarStack friends={friends.data ?? []} />
          </View>
        </View>

        <View style={{ marginTop: 14 }}>
          {tab === "friends" ? (
            <FriendsList query={friends} onChanged={refresh} />
          ) : tab === "requests" ? (
            <RequestsList query={requests} onChanged={refresh} />
          ) : (
            <FindStudents onChanged={refresh} />
          )}
        </View>
      </View>
    </Screen>
  );
}

/** Up to two faces plus a running total, overlapped the way the design stacks them. */
function AvatarStack({ friends }: { friends: Friend[] }) {
  if (!friends.length) return null;
  const shown = friends.slice(0, 2);
  const rest = friends.length - shown.length;

  return (
    <View style={s.stack}>
      {shown.map((f, i) => (
        <View key={f.id} style={[s.stackItem, i > 0 && { marginLeft: -9 }]}>
          <Avatar
            name={f.display_name}
            size={26}
            bg={i === 0 ? colors.brandTint : colors.avatarAlt}
          />
        </View>
      ))}
      {rest > 0 ? (
        <View style={[s.stackItem, s.stackRest, { marginLeft: -9 }]}>
          <Text style={s.stackRestText}>+{rest}</Text>
        </View>
      ) : null}
    </View>
  );
}

function TabChip({
  label,
  count,
  active,
  highlight,
  icon,
  onPress,
}: {
  label: string;
  count?: number;
  active: boolean;
  highlight?: boolean;
  icon?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.tab, active && s.tabActive, pressed && { opacity: 0.85 }]}
      accessibilityRole="tab"
      accessibilityState={{ selected: active }}
    >
      {icon ? (
        <Icon name="search" size={14} color={active ? colors.white : colors.muted} />
      ) : null}
      <Text style={[s.tabText, active && s.tabTextActive]}>{label}</Text>
      {count ? (
        <View style={[s.count, active && highlight && s.countHot]}>
          <Text style={[s.countText, active && highlight && s.countTextHot]}>{count}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

/* ------------------------------------------------------------------ friends */

function FriendsList({
  query,
  onChanged,
}: {
  query: UseQueryResult<Friend[]>;
  onChanged: () => void;
}) {
  if (query.isLoading) return <SkeletonRow />;
  const friends = query.data ?? [];

  if (!friends.length) {
    return (
      <EmptyState
        icon="connects"
        title="No friends yet"
        body="Find classmates and hostelmates under Find. Your errands will reach them before they reach strangers."
      />
    );
  }

  return (
    <View style={{ gap: space.sm }}>
      {friends.map((f) => (
        <View key={f.id} style={s.card}>
          <View style={s.personRow}>
            <Avatar name={f.display_name} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.name}>{f.display_name}</Text>
              <View style={s.ratingRow}>
                <Icon name="star" size={12} color={colors.brand} />
                <Text style={s.rating}>{f.reputation_score.toFixed(2)}</Text>
              </View>
            </View>
            <Pressable
              hitSlop={8}
              onPress={async () => {
                if (!(await confirm(`Remove ${f.display_name} from your friends?`))) return;
                try {
                  await unfriend(f.id);
                  onChanged();
                } catch (e) {
                  notify(apiErrorMessage(e, "Couldn't remove them."));
                }
              }}
            >
              <Text style={s.removeText}>Remove</Text>
            </Pressable>
          </View>
        </View>
      ))}
    </View>
  );
}

/* ----------------------------------------------------------------- requests */

function RequestsList({
  query,
  onChanged,
}: {
  query: UseQueryResult<PendingRequest[]>;
  onChanged: () => void;
}) {
  if (query.isLoading) return <SkeletonRow />;
  const requests = query.data ?? [];

  if (!requests.length) {
    return (
      <EmptyState icon="mail" title="No requests" body="Nobody is waiting on you right now." />
    );
  }

  return (
    <>
      <View style={s.waitingHead}>
        <Text style={s.waitingTitle}>Waiting on you</Text>
        <Text style={s.waitingCount}>
          {requests.length} request{requests.length === 1 ? "" : "s"}
        </Text>
      </View>

      <View style={{ gap: space.sm, marginTop: 10 }}>
        {requests.map((r) => (
          <View key={r.id} style={[s.card, shadow.card]}>
            <View style={s.personRow}>
              <Avatar name={r.from_user.display_name} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.name}>{r.from_user.display_name}</Text>
                <View style={s.ratingRow}>
                  <Icon name="star" size={12} color={colors.brand} />
                  <Text style={s.rating}>{r.from_user.reputation_score.toFixed(2)}</Text>
                </View>
              </View>
              <Text style={s.ago}>{timeAgo(r.created_at)}</Text>
            </View>

            <View style={s.requestActions}>
              <Button
                title="Accept"
                icon="check"
                style={{ flex: 1, height: 42 }}
                onPress={async () => {
                  try {
                    await respondToRequest(r.id, true);
                    onChanged();
                  } catch (e) {
                    notify(apiErrorMessage(e, "Couldn't accept."));
                  }
                }}
              />
              <Button
                title="Decline"
                variant="outline"
                style={{ flex: 1, height: 42 }}
                onPress={async () => {
                  try {
                    await respondToRequest(r.id, false);
                    onChanged();
                  } catch (e) {
                    notify(apiErrorMessage(e, "Couldn't decline."));
                  }
                }}
              />
            </View>
          </View>
        ))}
      </View>
    </>
  );
}

/* --------------------------------------------------------------------- find */

function FindStudents({ onChanged }: { onChanged: () => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<Record<string, boolean>>({});

  // Debounced so a search fires on a pause in typing, not on every keystroke.
  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setResults([]);
      return;
    }
    setBusy(true);
    const t = setTimeout(async () => {
      try {
        setResults(await searchStudents(term));
      } catch {
        setResults([]);
      } finally {
        setBusy(false);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <View style={{ gap: space.md }}>
      <Field
        label="Find students"
        icon="search"
        placeholder="Name or registration number"
        value={q}
        onChangeText={setQ}
        autoCapitalize="none"
        autoCorrect={false}
      />

      {busy ? <SkeletonRow /> : null}

      {!busy && q.trim().length >= 2 && !results.length ? (
        <EmptyState
          icon="search"
          title="Nobody found"
          body="Try a different name or registration number."
        />
      ) : null}

      {results.map((r) => (
        <View key={r.id} style={s.card}>
          <View style={s.personRow}>
            <Avatar name={r.display_name} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.name}>{r.display_name}</Text>
              {/* Registration number always shown: several students share a
                  display name, and this is the only way to tell which one. */}
              <Text numberOfLines={1} style={s.studentId}>
                {r.student_id ?? "—"}
              </Text>
            </View>
            <AddButton
              result={r}
              sent={!!sent[r.id]}
              onSent={() => {
                setSent((p) => ({ ...p, [r.id]: true }));
                onChanged();
              }}
            />
          </View>

          {r.mutual_friends > 0 ? (
            <View style={s.mutual}>
              <Icon name="connects" size={15} color={colors.brand} />
              <Text style={s.mutualText}>
                {r.mutual_friends} mutual friend{r.mutual_friends > 1 ? "s" : ""}
              </Text>
            </View>
          ) : (
            <View style={s.mutual}>
              <Icon name="connects" size={15} color={colors.mutedCool} />
              <Text style={[s.mutualText, { color: colors.muted }]}>No mutual friends yet</Text>
            </View>
          )}
        </View>
      ))}
    </View>
  );
}

function AddButton({
  result,
  sent,
  onSent,
}: {
  result: SearchResult;
  sent: boolean;
  onSent: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const rel: Relationship = sent ? "PENDING_OUT" : result.relationship;

  if (rel === "FRIENDS") return <Text style={s.stateText}>Friends</Text>;
  if (rel === "PENDING_OUT") return <Text style={s.stateText}>Requested</Text>;
  if (rel === "BLOCKED") return <Text style={s.stateText}>Blocked</Text>;

  return (
    <Button
      title={rel === "PENDING_IN" ? "Accept" : "Add"}
      full={false}
      style={{ height: 38, paddingHorizontal: 18 }}
      loading={busy}
      onPress={async () => {
        setBusy(true);
        try {
          // Sending back to someone who already asked accepts it, server side.
          await sendRequest(result.id);
          onSent();
        } catch (e) {
          notify(apiErrorMessage(e, "Couldn't send that request."));
        } finally {
          setBusy(false);
        }
      }}
    />
  );
}

const s = StyleSheet.create({
  body: { paddingHorizontal: 22, paddingTop: 18 },

  tabs: { flexDirection: "row", gap: 8 },
  tab: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
  },
  tabActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  tabText: { color: colors.muted, fontSize: 12.5, fontFamily: font.bold },
  tabTextActive: { color: colors.white },

  count: {
    minWidth: 18,
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: radius.pill,
    backgroundColor: colors.chip,
    alignItems: "center",
  },
  countHot: { backgroundColor: colors.moneyLight },
  countText: { fontSize: 11, fontFamily: font.bold, color: colors.muted },
  countTextHot: { color: colors.brandDeep },

  reach: {
    marginTop: 14,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.card,
    padding: 13,
  },
  reachHead: { flexDirection: "row", alignItems: "center", gap: 8 },
  reachTitle: { color: colors.ink, fontSize: 13, fontFamily: font.bold },
  reachRow: { flexDirection: "row", alignItems: "flex-end", gap: 14, marginTop: 11 },
  reachValue: { color: colors.ink, fontSize: 24, fontFamily: font.black, letterSpacing: -0.7 },
  reachLabel: { color: colors.muted, fontSize: 11, fontFamily: font.regular },
  reachRule: { width: 1, height: 30, backgroundColor: colors.hairline },

  stack: { marginLeft: "auto", flexDirection: "row", alignItems: "center" },
  stackItem: { borderWidth: 2, borderColor: colors.white, borderRadius: 15 },
  stackRest: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
  stackRestText: { color: colors.white, fontSize: 10, fontFamily: font.black },

  card: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.xxl,
    padding: 13,
  },
  personRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  name: { color: colors.ink, fontSize: 14.5, fontFamily: font.bold },
  ratingRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  rating: { color: colors.muted, fontSize: 11.5, fontFamily: font.semi },
  studentId: { color: colors.mutedCool, fontSize: 11, fontFamily: font.mono, marginTop: 2 },
  ago: { color: colors.mutedCool, fontSize: 11, fontFamily: font.regular },
  removeText: { color: colors.muted, fontSize: 12.5, fontFamily: font.semi },
  stateText: { color: colors.muted, fontSize: 12.5, fontFamily: font.semi },

  mutual: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 10,
    paddingHorizontal: 11,
    paddingVertical: 8,
    borderRadius: radius.md,
    backgroundColor: colors.bgSoft,
  },
  mutualText: { color: colors.inkSoft, fontSize: 11.5, fontFamily: font.regular },

  waitingHead: { flexDirection: "row", alignItems: "center", gap: 8 },
  waitingTitle: { color: colors.ink, fontSize: 15, fontFamily: font.black, letterSpacing: -0.3 },
  waitingCount: { color: colors.mutedCool, fontSize: 11.5, fontFamily: font.regular },

  requestActions: { flexDirection: "row", gap: 10, marginTop: 13 },
});
