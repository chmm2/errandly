import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { fetchMe } from "../../src/api/auth";
import { fetchNotifications } from "../../src/api/notifications";
import {
  cancelErrand,
  completeErrand,
  type Errand,
  type ErrandStatus,
  fetchMyErrands,
} from "../../src/api/errands";
import {
  Body,
  Button,
  Caption,
  Card,
  Footer,
  Heading,
  Hero,
  IconTile,
  Loading,
  Pill,
  Row,
  Screen,
} from "../../src/components/ui";
import { useSocket } from "../../src/lib/ws";
import { useAuth } from "../../src/stores/auth";
import {
  categoryIcon,
  colors,
  ETA_MINUTES,
  font,
  minsAgo,
  radius,
  rupees,
  space,
  startOptions,
  statusStyle,
} from "../../src/theme";

const LIVE_STATUSES: ErrandStatus[] = ["OPEN", "ACCEPTED", "IN_PROGRESS", "DELIVERED"];

/** Ticks so the "posted N min ago" / ETA line stays honest without a refetch. */
function useNow(intervalMs = 20_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

/** Live "how long" line — time since posting, or an ETA once accepted. */
function EtaLine({ errand }: { errand: Errand }) {
  const now = useNow();

  if (errand.status === "OPEN") {
    const m = minsAgo(errand.created_at);
    return (
      <Text style={[s.eta, { color: colors.amberText }]}>
        ⏳ Finding a runner · posted {m === 0 ? "just now" : `${m} min ago`}
      </Text>
    );
  }
  if (errand.status === "ACCEPTED" || errand.status === "IN_PROGRESS") {
    const base = errand.accepted_at ? new Date(errand.accepted_at).getTime() : now;
    const remaining = Math.round((base + ETA_MINUTES * 60_000 - now) / 60_000);
    return (
      <Text style={[s.eta, { color: colors.brandDark }]}>
        ⏱️ {remaining > 1 ? `ETA ~${remaining} min` : "Arriving any moment"}
      </Text>
    );
  }
  if (errand.status === "DELIVERED") {
    return (
      <Text style={[s.eta, { color: colors.purpleText }]}>✅ Handed over — confirm to close</Text>
    );
  }
  return null;
}

function ErrandRow({ errand, onRate }: { errand: Errand; onRate: (id: string) => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["my-errands"] });

  const cancel = useMutation({ mutationFn: () => cancelErrand(errand.id), onSettled: refresh });
  const confirm = useMutation({
    mutationFn: () => completeErrand(errand.id),
    onSuccess: () => onRate(errand.id),
    onSettled: refresh,
  });

  const status = statusStyle[errand.status];
  const cancellable = errand.status === "OPEN" || errand.status === "ACCEPTED";

  // Live status: the backend publishes every transition to this errand's
  // channel; refetch the moment one arrives (polling stays as fallback).
  useSocket(
    LIVE_STATUSES.includes(errand.status) ? `/ws/errands/${errand.id}` : null,
    useCallback(() => refresh(), [queryClient]),
  );

  return (
    <Card raised style={{ padding: space.lg }}>
      <Pressable onPress={() => router.push(`/errand/${errand.id}`)}>
        <Row gap={space.md} align="flex-start">
          <IconTile emoji={categoryIcon[errand.category] ?? "✨"} />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Body numberOfLines={1} style={{ fontFamily: font.bold }}>
              {errand.title}
            </Body>
            <Caption numberOfLines={1} style={{ marginTop: 2 }}>
              from {errand.pickup_label} · {rupees(errand.reward)} reward · track →
            </Caption>
            <View style={{ marginTop: 5 }}>
              <EtaLine errand={errand} />
            </View>
          </View>
        </Row>
      </Pressable>

      <Row gap={space.sm} wrap style={{ marginTop: space.md }}>
        <Pill label={status.label} bg={status.bg} color={status.text} />

        {errand.status === "DELIVERED" ? (
          <Button
            title="Confirm ✓"
            variant="success"
            full={false}
            loading={confirm.isPending}
            onPress={() => confirm.mutate()}
            style={s.rowBtn}
          />
        ) : null}

        {errand.status === "COMPLETED" && !errand.rated ? (
          <Button
            title="Rate ★"
            variant="outline"
            full={false}
            onPress={() => onRate(errand.id)}
            style={s.rowBtn}
          />
        ) : null}

        {cancellable ? (
          <Pressable
            onPress={() => cancel.mutate()}
            disabled={cancel.isPending}
            style={{ marginLeft: "auto", justifyContent: "center" }}
            hitSlop={8}
          >
            <Caption style={{ fontFamily: font.semi }}>
              {cancel.isPending ? "Cancelling…" : "Cancel"}
            </Caption>
          </Pressable>
        ) : null}
      </Row>
    </Card>
  );
}

export default function Home() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setUser);

  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  useEffect(() => {
    if (me) setUser(me);
  }, [me, setUser]);

  const { data: mine, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ["my-errands"],
    queryFn: fetchMyErrands,
    refetchInterval: 15_000,
  });

  const { data: notifications } = useQuery({
    queryKey: ["notifications"],
    queryFn: fetchNotifications,
    refetchInterval: 60_000,
  });
  const unread = notifications?.unread ?? 0;

  const active = (mine?.requested ?? []).filter(
    (e) => !["COMPLETED", "CANCELLED", "EXPIRED"].includes(e.status),
  );

  // You can't order while mid-delivery for someone else — the backend rejects
  // it, so don't offer the button. Same rule the web's Order/Run lock enforces.
  const onActiveRun = (mine?.running ?? []).some((e) =>
    ["ACCEPTED", "IN_PROGRESS"].includes(e.status),
  );

  const firstName = user?.display_name?.split(" ")[0] ?? "there";

  return (
    <Screen
      scroll
      padded={false}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
      }
    >
      <Hero
        title={`Hey ${firstName}, what do you need today?`}
        subtitle="A verified student runner is minutes away. Post an errand or pick one up on your way back to the hostel."
      >
        {onActiveRun ? (
          <View style={s.lockNote}>
            <Text style={s.lockText}>
              🛵 Finish the run you're on before posting your own errand.
            </Text>
          </View>
        ) : (
          <Button
            title="Post an errand  →"
            variant="white"
            full={false}
            onPress={() => router.push("/errand/new")}
            style={{ marginTop: space.xl, alignSelf: "flex-start" }}
          />
        )}
      </Hero>

      {/* Bell sits over the hero, same position the web navbar puts it. */}
      <Pressable onPress={() => router.push("/notifications")} style={s.bell} hitSlop={10}>
        <Text style={{ fontSize: 17 }}>🔔</Text>
        {unread > 0 ? (
          <View style={s.badge}>
            <Text style={s.badgeText}>{unread > 9 ? "9+" : unread}</Text>
          </View>
        ) : null}
      </Pressable>

      <View style={{ paddingHorizontal: space.lg }}>
        {/* Active errands first — the moment something's in flight, it's the
            top thing you want to see. */}
        {isLoading ? (
          <View style={{ height: 150 }}>
            <Loading />
          </View>
        ) : active.length > 0 ? (
          <View style={{ paddingTop: space.xxl }}>
            <Heading>Your active errands</Heading>
            <View style={{ gap: space.md, marginTop: space.lg }}>
              {active.map((e) => (
                <ErrandRow key={e.id} errand={e} onRate={(id) => router.push(`/errand/${id}`)} />
              ))}
            </View>
          </View>
        ) : null}

        {/* Start an errand */}
        <View style={{ paddingTop: space.xxl }}>
          <Heading>What can we get you?</Heading>
          <Row gap={space.md} wrap style={{ marginTop: space.lg }}>
            {startOptions.map((c) => (
              <Pressable
                key={c.name}
                disabled={onActiveRun}
                onPress={() => router.push({ pathname: c.route, params: c.params } as never)}
                style={({ pressed }) => [
                  s.startCard,
                  pressed && s.startCardOn,
                  onActiveRun && { opacity: 0.45 },
                ]}
              >
                <Text style={{ fontSize: 30 }}>{c.icon}</Text>
                <Body style={{ fontFamily: font.bold, marginTop: space.sm }}>{c.name}</Body>
                <Caption style={{ marginTop: 2 }}>{c.desc}</Caption>
              </Pressable>
            ))}
          </Row>

          {active.length === 0 && !isLoading ? (
            <Caption style={{ marginTop: space.lg }}>
              Nothing in flight right now — pick a category above to post your first errand. Past
              errands live in your profile.
            </Caption>
          ) : null}
        </View>

        <Footer />
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  lockNote: {
    marginTop: space.xl,
    alignSelf: "flex-start",
    backgroundColor: "rgba(255,255,255,0.2)",
    borderRadius: radius.lg,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  lockText: { color: colors.white, fontSize: font.small, fontFamily: font.semi },

  bell: {
    position: "absolute",
    top: space.xl,
    right: space.lg,
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: "rgba(255,255,255,0.22)",
    alignItems: "center",
    justifyContent: "center",
  },
  badge: {
    position: "absolute",
    top: -2,
    right: -2,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    paddingHorizontal: 4,
    backgroundColor: colors.white,
    alignItems: "center",
    justifyContent: "center",
  },
  badgeText: { color: colors.brand, fontSize: 10, fontFamily: font.black },

  eta: { fontSize: font.tiny, fontFamily: font.semi },
  rowBtn: { height: 36, paddingHorizontal: space.lg },

  startCard: {
    width: "48%",
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
    padding: space.lg,
    minHeight: 132,
  },
  startCardOn: { borderColor: colors.brand, opacity: 0.9 },
});
