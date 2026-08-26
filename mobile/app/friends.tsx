import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import {
  blockUser,
  fetchFriends,
  fetchRequests,
  respondToRequest,
  searchStudents,
  sendRequest,
  unfriend,
  type Friend,
  type Relationship,
  type SearchResult,
} from "../src/api/social";
import {
  Body,
  Button,
  Caption,
  Card,
  EmptyState,
  Field,
  Hero,
  Loading,
  Row,
  Screen,
  Title,
} from "../src/components/ui";
import { apiErrorMessage } from "../src/lib/api";
import { confirm, notify } from "../src/lib/dialog";
import { colors, font, radius, space } from "../src/theme";

type Tab = "friends" | "requests" | "find";

export default function Friends() {
  const router = useRouter();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("friends");

  const friends = useQuery({ queryKey: ["friends"], queryFn: fetchFriends });
  const requests = useQuery({ queryKey: ["friend-requests"], queryFn: fetchRequests });

  const pendingCount = requests.data?.length ?? 0;

  function refresh() {
    qc.invalidateQueries({ queryKey: ["friends"] });
    qc.invalidateQueries({ queryKey: ["friend-requests"] });
  }

  return (
    <Screen scroll>
      <Hero
        eyebrow="Your circle"
        title="Friends"
        subtitle="Errands go to people you know first — friends, then friends of friends, before anyone else."
        onBack={() => router.back()}
      />

      <Row gap={space.sm} style={{ marginTop: space.xl }}>
        <TabButton label="Friends" count={friends.data?.length} active={tab === "friends"} onPress={() => setTab("friends")} />
        <TabButton label="Requests" count={pendingCount} active={tab === "requests"} onPress={() => setTab("requests")} highlight={pendingCount > 0} />
        <TabButton label="Find" active={tab === "find"} onPress={() => setTab("find")} />
      </Row>

      <View style={{ marginTop: space.xl }}>
        {tab === "friends" ? (
          <FriendsList query={friends} onChanged={refresh} />
        ) : tab === "requests" ? (
          <RequestsList query={requests} onChanged={refresh} />
        ) : (
          <FindStudents onChanged={refresh} />
        )}
      </View>
    </Screen>
  );
}

function TabButton({
  label,
  count,
  active,
  highlight,
  onPress,
}: {
  label: string;
  count?: number;
  active: boolean;
  highlight?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={[s.tab, active && s.tabActive]}>
      <Text style={[s.tabText, active && s.tabTextActive]}>{label}</Text>
      {count ? (
        <View style={[s.count, highlight && !active && s.countHot]}>
          <Text style={[s.countText, highlight && !active && s.countTextHot]}>{count}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

/* ------------------------------------------------------------------ friends */

function FriendsList({ query, onChanged }: { query: any; onChanged: () => void }) {
  if (query.isLoading) return <Loading />;
  const friends: Friend[] = query.data ?? [];

  if (!friends.length) {
    return (
      <EmptyState
        emoji="👋"
        title="No friends yet"
        body="Find classmates and hostelmates under Find. Your errands will reach them before they reach strangers."
      />
    );
  }

  return (
    <View style={{ gap: space.md }}>
      {friends.map((f) => (
        <Card key={f.id}>
          <Row gap={space.md}>
            <Avatar name={f.display_name} url={f.photo_url} />
            <View style={{ flex: 1 }}>
              <Text style={s.name}>{f.display_name}</Text>
              <Caption>⭐ {f.reputation_score.toFixed(1)}</Caption>
            </View>
            <Button
              title="Remove"
              variant="ghost"
              size="md"
              onPress={async () => {
                if (!(await confirm(`Remove ${f.display_name} from your friends?`))) return;
                try {
                  await unfriend(f.id);
                  onChanged();
                } catch (e) {
                  notify(apiErrorMessage(e, "Couldn't remove them."));
                }
              }}
            />
          </Row>
        </Card>
      ))}
    </View>
  );
}

/* ----------------------------------------------------------------- requests */

function RequestsList({ query, onChanged }: { query: any; onChanged: () => void }) {
  if (query.isLoading) return <Loading />;
  const requests = query.data ?? [];

  if (!requests.length) {
    return <EmptyState emoji="📭" title="No requests" body="Nobody's waiting on you right now." />;
  }

  return (
    <View style={{ gap: space.md }}>
      {requests.map((r: any) => (
        <Card key={r.id}>
          <Row gap={space.md}>
            <Avatar name={r.from_user.display_name} url={r.from_user.photo_url} />
            <View style={{ flex: 1 }}>
              <Text style={s.name}>{r.from_user.display_name}</Text>
              <Caption>wants to connect</Caption>
            </View>
          </Row>
          <Row gap={space.sm} style={{ marginTop: space.md }}>
            <View style={{ flex: 1 }}>
              <Button
                title="Accept"
                size="md"
                onPress={async () => {
                  try {
                    await respondToRequest(r.id, true);
                    onChanged();
                  } catch (e) {
                    notify(apiErrorMessage(e, "Couldn't accept."));
                  }
                }}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Button
                title="Decline"
                variant="outline"
                size="md"
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
          </Row>
        </Card>
      ))}
    </View>
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
    <View style={{ gap: space.lg }}>
      <Field
        label="Find students"
        placeholder="Name or registration number"
        value={q}
        onChangeText={setQ}
        autoCapitalize="none"
        autoCorrect={false}
      />

      {busy ? <Loading /> : null}

      {!busy && q.trim().length >= 2 && !results.length ? (
        <EmptyState emoji="🔍" title="Nobody found" body="Try a different name or registration number." />
      ) : null}

      {results.map((r) => (
        <Card key={r.id}>
          <Row gap={space.md}>
            <Avatar name={r.display_name} url={r.photo_url} />
            <View style={{ flex: 1 }}>
              <Text style={s.name}>{r.display_name}</Text>
              {/* Registration number always shown: several students share a
                  display name, and this is the only way to tell which one. */}
              <Caption numberOfLines={1}>
                {r.student_id ?? "—"}
                {r.mutual_friends > 0
                  ? ` · ${r.mutual_friends} mutual friend${r.mutual_friends > 1 ? "s" : ""}`
                  : ""}
              </Caption>
            </View>
            <AddButton
              result={r}
              sent={!!sent[r.id]}
              onSent={() => {
                setSent((p) => ({ ...p, [r.id]: true }));
                onChanged();
              }}
            />
          </Row>
        </Card>
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

  if (rel === "FRIENDS") return <Caption style={s.stateText}>Friends</Caption>;
  if (rel === "PENDING_OUT") return <Caption style={s.stateText}>Requested</Caption>;
  if (rel === "BLOCKED") return <Caption style={s.stateText}>Blocked</Caption>;

  return (
    <Button
      title={rel === "PENDING_IN" ? "Accept" : "Add"}
      size="md"
      loading={busy}
      onPress={async () => {
        setBusy(true);
        try {
          // Sending back to someone who already asked accepts it, server-side.
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

/* ------------------------------------------------------------------- shared */

function Avatar({ name, url }: { name: string; url: string | null }) {
  const initial = (name || "?").trim().charAt(0).toUpperCase();
  if (url) {
    return <View style={s.avatar}><Text style={s.avatarText}>{initial}</Text></View>;
  }
  return (
    <View style={s.avatar}>
      <Text style={s.avatarText}>{initial}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  tab: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: space.md,
    paddingVertical: 9,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
  },
  tabActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  tabText: { color: colors.muted, fontSize: font.small, fontFamily: font.bold },
  tabTextActive: { color: colors.white },

  count: {
    minWidth: 20,
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: radius.pill,
    backgroundColor: colors.bgSoft,
    alignItems: "center",
  },
  countHot: { backgroundColor: colors.brand },
  countText: { fontSize: 11, fontFamily: font.black, color: colors.muted },
  countTextHot: { color: colors.white },

  name: { color: colors.ink, fontSize: font.body, fontFamily: font.bold },
  stateText: { color: colors.muted, fontFamily: font.semi },

  avatar: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { color: colors.brandDark, fontSize: 17, fontFamily: font.black },
});
