import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { fetchMe } from "../../src/api/auth";
import {
  cancelErrand,
  completeErrand,
  type Errand,
  type ErrandStatus,
  fetchMyErrands,
} from "../../src/api/errands";
import { fetchNotifications } from "../../src/api/notifications";
import { Icon, Mark } from "../../src/components/icons";
import {
  Button,
  Caption,
  Footer,
  Heading,
  Hero,
  HeroButton,
  IconTile,
  Screen,
  SkeletonRow,
} from "../../src/components/ui";
import { useSocket } from "../../src/lib/ws";
import { useAuth } from "../../src/stores/auth";
import {
  categoryIcon,
  colors,
  ETA_MINUTES,
  font,
  minsAgo,
  onBrand,
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

/**
 * How far along the strip under an errand should be filled. These are the five
 * steps the tracking screen names, collapsed to a fraction.
 */
const PROGRESS: Partial<Record<ErrandStatus, number>> = {
  OPEN: 0.2,
  ACCEPTED: 0.4,
  IN_PROGRESS: 0.64,
  DELIVERED: 0.85,
  COMPLETED: 1,
};

/** Live "how long" line: time since posting, or an ETA once accepted. */
function EtaLine({ errand }: { errand: Errand }) {
  const now = useNow();

  if (errand.status === "OPEN") {
    const m = minsAgo(errand.created_at);
    return (
      <Line icon="clock" color={colors.warnText}>
        Finding a runner, posted {m === 0 ? "just now" : `${m} min ago`}
      </Line>
    );
  }
  if (errand.status === "ACCEPTED" || errand.status === "IN_PROGRESS") {
    const base = errand.accepted_at ? new Date(errand.accepted_at).getTime() : now;
    const remaining = Math.round((base + ETA_MINUTES * 60_000 - now) / 60_000);
    return (
      <Line icon="clock" color={colors.brand}>
        {remaining > 1 ? `Arriving in about ${remaining} min` : "Arriving any moment"}
      </Line>
    );
  }
  if (errand.status === "DELIVERED") {
    return (
      <Line icon="check" color={colors.warnText}>
        Handed over, confirm to close
      </Line>
    );
  }
  return null;
}

function Line({
  icon,
  color,
  children,
}: {
  icon: "clock" | "check";
  color: string;
  children: React.ReactNode;
}) {
  return (
    <View style={s.etaRow}>
      <Icon name={icon} size={15} color={color} />
      <Text style={[s.eta, { color }]}>{children}</Text>
    </View>
  );
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
  const progress = PROGRESS[errand.status] ?? 0;

  // Live status: the backend publishes every transition to this errand's
  // channel; refetch the moment one arrives (polling stays as fallback).
  useSocket(
    LIVE_STATUSES.includes(errand.status) ? `/ws/errands/${errand.id}` : null,
    useCallback(() => refresh(), [queryClient]),
  );

  return (
    <View style={s.flightCard}>
      <Pressable onPress={() => router.push(`/errand/${errand.id}`)}>
        <View style={s.flightTop}>
          <IconTile icon={categoryIcon[errand.category] ?? "gate"} size={46} />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text numberOfLines={1} style={s.flightTitle}>
              {errand.title}
            </Text>
            <Text numberOfLines={1} style={s.flightSub}>
              {errand.pickup_label}
              {errand.runner ? `, ${errand.runner.display_name} running it` : ""}
            </Text>
            <View style={{ marginTop: 8 }}>
              <EtaLine errand={errand} />
            </View>
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <Text style={s.reward}>{rupees(errand.reward)}</Text>
            <Text style={s.rewardLabel}>reward</Text>
          </View>
        </View>
      </Pressable>

      <View style={s.flightFoot}>
        <View style={[s.statusPill, { backgroundColor: status.bg }]}>
          <Icon name="bike" size={13} color={status.text} />
          <Text style={[s.statusText, { color: status.text }]}>{status.label}</Text>
        </View>

        <View style={s.track}>
          <View style={[s.trackFill, { width: `${Math.round(progress * 100)}%` }]} />
        </View>

        <Pressable
          onPress={() => router.push(`/errand/${errand.id}`)}
          hitSlop={8}
          style={s.trackLink}
        >
          <Text style={s.trackLinkText}>Track</Text>
          <Icon name="chev" size={14} color={colors.brand} />
        </Pressable>
      </View>

      {errand.status === "DELIVERED" || (errand.status === "COMPLETED" && !errand.rated) || cancellable ? (
        <View style={s.flightActions}>
          {errand.status === "DELIVERED" ? (
            <Button
              title="Confirm"
              icon="check"
              full={false}
              loading={confirm.isPending}
              onPress={() => confirm.mutate()}
              style={s.rowBtn}
            />
          ) : null}

          {errand.status === "COMPLETED" && !errand.rated ? (
            <Button
              title="Rate"
              icon="star"
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
              <Text style={s.cancelText}>
                {cancel.isPending ? "Cancelling…" : "Cancel"}
              </Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

export default function Home() {
  const router = useRouter();
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

  // You can't order while mid-delivery for someone else: the backend rejects
  // it, so don't offer the button. Same rule the web's Order/Run lock enforces.
  const onActiveRun = (mine?.running ?? []).some((e) =>
    ["ACCEPTED", "IN_PROGRESS"].includes(e.status),
  );

  const firstName = user?.display_name?.split(" ")[0] ?? "there";

  return (
    <Screen
      scroll
      padded={false}
      edges={[]}
      bg={colors.white}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
      }
    >
      <Hero
        title={`Hey ${firstName}, what do you need today?`}
        right={
          <HeroButton
            icon="bell"
            badge={unread}
            label="Notifications"
            onPress={() => router.push("/notifications")}
          />
        }
      >
        <View style={s.campusRow}>
          <Mark size={22} color={onBrand.text} weight={6} />
          <Text style={s.campus}>Katpadi campus</Text>
        </View>

        {onActiveRun ? (
          <View style={s.lockNote}>
            <Icon name="bike" size={15} color={colors.white} />
            <Text style={s.lockText}>
              Finish the run you're on before posting your own errand.
            </Text>
          </View>
        ) : null}
      </Hero>

      <View style={s.body}>
        {/* Starting an errand is why you opened the app, so it leads. */}
        <Pressable
          disabled={onActiveRun}
          onPress={() => router.push({ pathname: "/errand/new", params: { mode: "shopping" } })}
          style={({ pressed }) => [s.search, pressed && { borderColor: colors.brand }]}
        >
          <Icon name="search" size={20} color={colors.brand} />
          <Text style={s.searchText}>Milk, printouts, a parcel at the gate</Text>
          <View style={s.searchPlus}>
            <Icon name="plus" size={17} color={colors.white} />
          </View>
        </Pressable>

        {isLoading ? (
          <View style={{ marginTop: space.lg, gap: space.sm }}>
            <SkeletonRow />
            <SkeletonRow />
          </View>
        ) : active.length > 0 ? (
          <>
            <View style={s.sectionHead}>
              <Heading>In flight</Heading>
              <Text style={s.sectionCount}>
                {active.length} errand{active.length === 1 ? "" : "s"}
              </Text>
            </View>
            <View style={{ gap: space.sm, marginTop: 11 }}>
              {active.map((e) => (
                <ErrandRow key={e.id} errand={e} onRate={(id) => router.push(`/errand/${id}`)} />
              ))}
            </View>
          </>
        ) : null}

        <View style={s.grid}>
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
              <IconTile icon={c.icon as never} size={40} />
              <View style={{ marginTop: 6 }}>
                <Text style={s.startName}>{c.name}</Text>
                <Text style={s.startDesc}>{c.desc}</Text>
              </View>
            </Pressable>
          ))}
        </View>

        {!isLoading && active.length === 0 ? (
          <Caption style={{ marginTop: space.lg }}>
            Nothing in flight right now. Pick a category above to post your first errand. Past
            errands live in your profile.
          </Caption>
        ) : null}

        <Footer />
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  campusRow: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 10 },
  campus: {
    color: onBrand.textDim,
    fontSize: font.tiny,
    fontFamily: font.bold,
    letterSpacing: 1.5,
    textTransform: "uppercase",
  },

  lockNote: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: space.lg,
    alignSelf: "flex-start",
    backgroundColor: onBrand.fill,
    borderRadius: radius.md,
    paddingHorizontal: 13,
    paddingVertical: 10,
  },
  lockText: { flex: 1, color: colors.white, fontSize: 12.5, fontFamily: font.semi },

  body: { paddingHorizontal: 22, paddingTop: 14 },

  search: {
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.xxl,
    paddingVertical: 12,
    paddingHorizontal: 15,
    backgroundColor: colors.white,
  },
  searchText: { flex: 1, color: colors.mutedCool, fontSize: 14.5, fontFamily: font.regular },
  searchPlus: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },

  sectionHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: space.lg,
  },
  sectionCount: { color: colors.muted, fontSize: 12, fontFamily: font.semi },

  flightCard: {
    borderWidth: 1,
    borderColor: colors.lineStrong,
    borderRadius: radius.xxl,
    padding: 14,
    backgroundColor: colors.white,
  },
  flightTop: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  flightTitle: { color: colors.ink, fontSize: 14.5, fontFamily: font.bold },
  flightSub: { color: colors.muted, fontSize: 12, fontFamily: font.regular, marginTop: 2 },
  reward: { color: colors.moneyText, fontSize: 19, fontFamily: font.black, letterSpacing: -0.4 },
  rewardLabel: { color: colors.mutedCool, fontSize: 10, fontFamily: font.regular },

  etaRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  eta: { fontSize: 12, fontFamily: font.bold },

  flightFoot: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 11,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
  },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 11,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  statusText: { fontSize: 11, fontFamily: font.bold },
  track: { flex: 1, height: 4, borderRadius: 2, backgroundColor: colors.hairline, overflow: "hidden" },
  trackFill: { height: "100%", borderRadius: 2, backgroundColor: colors.brand },
  trackLink: { flexDirection: "row", alignItems: "center", gap: 4 },
  trackLinkText: { color: colors.brand, fontSize: 12, fontFamily: font.bold },

  flightActions: { flexDirection: "row", gap: space.sm, marginTop: space.md, alignItems: "center" },
  rowBtn: { height: 38, paddingHorizontal: space.lg },
  cancelText: { color: colors.muted, fontSize: 12, fontFamily: font.semi },

  grid: { flexDirection: "row", flexWrap: "wrap", gap: 9, marginTop: 12 },
  startCard: {
    width: "48.4%",
    borderRadius: radius.xxl,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
    padding: 13,
    minHeight: 116,
  },
  startCardOn: { borderColor: colors.brand },
  startName: { color: colors.ink, fontSize: 14.5, fontFamily: font.bold },
  startDesc: {
    color: colors.muted,
    fontSize: 12,
    fontFamily: font.regular,
    lineHeight: 17,
    marginTop: 2,
  },
});
