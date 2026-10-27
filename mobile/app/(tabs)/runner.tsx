import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Location from "expo-location";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Animated,
  Easing,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { acceptErrand, type Errand, fetchFeed, fetchMyErrands } from "../../src/api/errands";
import { fetchEarnings } from "../../src/api/ledger";
import { fetchRunnerProfile, setAvailability, updateLocation } from "../../src/api/runners";
import type { Connection } from "../../src/api/social";
import { ConnectionBadge } from "../../src/components/ConnectionBadge";
import { ErrandCard } from "../../src/components/ErrandCard";
import { Icon } from "../../src/components/icons";
import {
  Button,
  EmptyState,
  Heading,
  Hero,
  PulseRing,
  Screen,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { notify } from "../../src/lib/dialog";
import { useSocket } from "../../src/lib/ws";
import { colors, font, metres, onBrand, radius, rupees, shadow, space } from "../../src/theme";

interface Offer {
  errand_id: string;
  title: string;
  category: string;
  reward: number;
  distance_m?: number;
  /** How you know the poster, rides along with the offer over pub/sub. */
  connection?: Connection | null;
}

/** Matches the web client's 10s send throttle. */
const LOCATION_SEND_MS = 10_000;
const ACTIVE = ["ACCEPTED", "IN_PROGRESS", "DELIVERED"];

export default function Runner() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [geo, setGeo] = useState<{ lat: number; lng: number } | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [toggling, setToggling] = useState(false);
  const lastSent = useRef(0);

  const { data: profile } = useQuery({ queryKey: ["runner-profile"], queryFn: fetchRunnerProfile });
  const available = profile?.is_available ?? false;

  const { data: earnings } = useQuery({ queryKey: ["earnings"], queryFn: fetchEarnings });

  const { data: feed, refetch, isRefetching } = useQuery({
    queryKey: ["runner-feed", geo?.lat, geo?.lng],
    queryFn: () => fetchFeed(20, 0, geo ?? undefined),
    enabled: available,
    refetchInterval: 20_000,
  });

  const { data: mine } = useQuery({ queryKey: ["my-errands"], queryFn: fetchMyErrands });
  const activeRuns = (mine?.running ?? []).filter((e) => ACTIVE.includes(e.status));

  /* ---- live location while available -------------------------------- */
  useEffect(() => {
    if (!available) return;
    let sub: Location.LocationSubscription | null = null;
    let cancelled = false;

    (async () => {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted" || cancelled) return;
      sub = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.High, distanceInterval: 15 },
        (pos) => {
          const loc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
          setGeo(loc);
          const now = Date.now();
          if (now - lastSent.current < LOCATION_SEND_MS) return;
          lastSent.current = now;
          updateLocation(loc.lat, loc.lng).catch(() => {});
        },
      );
    })();

    return () => {
      cancelled = true;
      sub?.remove();
    };
  }, [available]);

  /* ---- live offers pushed by the matching engine --------------------- */
  useSocket(
    available ? "/ws/runner" : null,
    useCallback((data: Record<string, unknown>) => {
      if (data.type !== "offer") return;
      const offer = data as unknown as Offer;
      setOffers((prev) =>
        prev.some((o) => o.errand_id === offer.errand_id) ? prev : [offer, ...prev].slice(0, 5),
      );
    }, []),
  );

  async function toggle(next: boolean) {
    setToggling(true);
    try {
      if (!next) {
        await setAvailability(false);
        setOffers([]);
      } else {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status !== "granted") {
          notify(
            "Location needed",
            "Errandly matches you with errands near you, so run mode needs location access.",
          );
          return;
        }
        const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
        const loc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setGeo(loc);
        await setAvailability(true, loc);
      }
      await queryClient.invalidateQueries({ queryKey: ["runner-profile"] });
    } catch (err) {
      notify("Couldn't update", apiErrorMessage(err));
    } finally {
      setToggling(false);
    }
  }

  const accept = useMutation({
    mutationFn: acceptErrand,
    onSuccess: (errand) => {
      setOffers((prev) => prev.filter((o) => o.errand_id !== errand.id));
      queryClient.invalidateQueries({ queryKey: ["my-errands"] });
      queryClient.invalidateQueries({ queryKey: ["runner-feed"] });
      router.push(`/errand/${errand.id}`);
    },
    onError: (err) => notify("Couldn't accept", apiErrorMessage(err)),
  });

  const nearby = (feed?.items ?? []).filter((e) => !activeRuns.some((r) => r.id === e.id));

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
      <Hero
        compact
        title="Run mode"
        subtitle="Earn on the trip back to your hostel that you were making anyway."
        right={
          <View style={s.heroTile}>
            <Icon name="bike" size={28} color={colors.white} />
          </View>
        }
      />

      <View style={s.body}>
        {/* Online switch and earnings */}
        <View style={[s.card, shadow.card]}>
          <View style={s.onlineRow}>
            <View style={{ flex: 1 }}>
              <View style={s.onlineHead}>
                <View style={s.dotWrap}>
                  {available ? <PulseRing color={colors.credit} duration={2200} /> : null}
                  <View
                    style={[s.dot, { backgroundColor: available ? colors.credit : colors.muted }]}
                  />
                </View>
                <Text style={s.onlineTitle}>
                  {available ? "You are online" : "You are offline"}
                </Text>
              </View>
              <Text style={s.onlineNote}>
                {available
                  ? "Nearby errands ping you instantly."
                  : "Go online to start receiving offers."}
              </Text>
            </View>
            <Toggle value={available} onChange={toggle} disabled={toggling} />
          </View>

          <View style={s.stats}>
            <Stat value={rupees(earnings?.balance ?? 0)} label="balance" />
            <Stat value={rupees(earnings?.week_total ?? 0)} label="this week" />
            <Stat value={String(earnings?.week_runs ?? 0)} label="runs" />
          </View>
        </View>

        {/* Live offers */}
        {offers.length > 0 ? (
          <>
            <View style={s.liveHead}>
              <Icon name="bolt" size={18} color={colors.brand} />
              <Heading>
                Live offer{offers.length === 1 ? "" : "s"} for you
              </Heading>
            </View>

            <View style={{ gap: space.md, marginTop: 12 }}>
              {offers.map((o) => (
                <View key={o.errand_id} style={s.offer}>
                  <View style={s.offerTop}>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <View style={s.offerTitleRow}>
                        <Text numberOfLines={1} style={s.offerTitle}>
                          {o.title}
                        </Text>
                        <ConnectionBadge connection={o.connection} />
                      </View>
                      <Text style={s.offerSub}>
                        {o.connection?.degree === 1
                          ? "From a friend"
                          : o.connection?.via
                            ? `Through ${o.connection.via}`
                            : "Nearby"}
                        {o.distance_m != null ? `, ${metres(o.distance_m)} away` : ""}
                      </Text>
                    </View>
                    <View style={{ alignItems: "flex-end" }}>
                      <Text style={s.offerReward}>{rupees(o.reward)}</Text>
                      <Text style={s.rewardLabel}>reward</Text>
                    </View>
                  </View>

                  <View style={s.offerActions}>
                    <Button
                      title="Accept"
                      icon="check"
                      loading={accept.isPending && accept.variables === o.errand_id}
                      onPress={() => accept.mutate(o.errand_id)}
                      style={{ flex: 1 }}
                    />
                    <Button
                      title="Skip"
                      variant="outline"
                      full={false}
                      onPress={() =>
                        setOffers((prev) => prev.filter((x) => x.errand_id !== o.errand_id))
                      }
                      style={{ width: 104 }}
                    />
                  </View>
                </View>
              ))}
            </View>
          </>
        ) : null}

        {/* Active runs */}
        {activeRuns.length > 0 ? (
          <>
            <Heading style={{ marginTop: space.xxl }}>Your active runs</Heading>
            <View style={{ gap: space.md, marginTop: 12 }}>
              {activeRuns.map((e) => (
                <ErrandCard key={e.id} errand={e} onPress={() => router.push(`/errand/${e.id}`)} />
              ))}
            </View>
          </>
        ) : null}

        {/* Nearby feed */}
        <Heading style={{ marginTop: 24, marginBottom: 12 }}>Nearby errands</Heading>
        {!available ? (
          <EmptyState
            icon="bike"
            title="You are offline"
            body="Flip the switch above to see errands around you and get live offers."
          />
        ) : nearby.length === 0 ? (
          <EmptyState
            icon="moon"
            title="Nothing nearby yet"
            body="New errands appear the moment someone posts one."
          />
        ) : (
          <View style={{ gap: space.md }}>
            {nearby.map((e: Errand) => (
              <ErrandCard
                key={e.id}
                errand={e}
                showStatus={false}
                onPress={() => router.push(`/errand/${e.id}`)}
                onAccept={() => accept.mutate(e.id)}
                accepting={accept.isPending && accept.variables === e.id}
              />
            ))}
          </View>
        )}
      </View>
    </Screen>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={s.statValue}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

/**
 * The availability switch. Built by hand rather than with the platform Switch,
 * because the design fixes its size and the platform control cannot be resized
 * on either OS.
 */
function Toggle({
  value,
  onChange,
  disabled,
}: {
  value: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  const t = useRef(new Animated.Value(value ? 1 : 0)).current;

  useEffect(() => {
    Animated.timing(t, {
      toValue: value ? 1 : 0,
      duration: 180,
      easing: Easing.out(Easing.ease),
      useNativeDriver: true,
    }).start();
  }, [t, value]);

  const translateX = t.interpolate({ inputRange: [0, 1], outputRange: [0, 23] });

  return (
    <Pressable
      onPress={() => onChange(!value)}
      disabled={disabled}
      accessibilityRole="switch"
      aria-checked={value}
      aria-disabled={disabled}
      accessibilityLabel="Availability"
      style={[
        s.toggle,
        { backgroundColor: value ? colors.brand : colors.lineStrong },
        disabled && { opacity: 0.6 },
      ]}
    >
      <Animated.View style={[s.thumb, { transform: [{ translateX }] }]} />
    </Pressable>
  );
}

const s = StyleSheet.create({
  heroTile: {
    width: 52,
    height: 52,
    borderRadius: radius.xl,
    backgroundColor: onBrand.fill,
    alignItems: "center",
    justifyContent: "center",
  },

  body: { paddingHorizontal: 22, paddingTop: 18 },

  card: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.card,
    padding: 18,
  },
  onlineRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 14 },
  onlineHead: { flexDirection: "row", alignItems: "center", gap: 8 },
  dotWrap: { width: 9, height: 9, alignItems: "center", justifyContent: "center" },
  dot: { width: 9, height: 9, borderRadius: 4.5 },
  onlineTitle: { color: colors.ink, fontSize: 15, fontFamily: font.bold },
  onlineNote: { color: colors.muted, fontSize: 12, fontFamily: font.regular, marginTop: 3 },

  toggle: {
    width: 54,
    height: 31,
    borderRadius: 16,
    padding: 3,
    justifyContent: "center",
  },
  thumb: {
    width: 25,
    height: 25,
    borderRadius: 12.5,
    backgroundColor: colors.white,
    shadowColor: "#000",
    shadowOpacity: 0.25,
    shadowRadius: 5,
    shadowOffset: { width: 0, height: 2 },
    elevation: 3,
  },

  stats: {
    flexDirection: "row",
    gap: 8,
    marginTop: space.lg,
    paddingTop: space.lg,
    borderTopWidth: 1,
    borderTopColor: colors.hairlineSoft,
  },
  statValue: { color: colors.ink, fontSize: 18, fontFamily: font.black, letterSpacing: -0.4 },
  statLabel: { color: colors.muted, fontSize: 11, fontFamily: font.regular },

  liveHead: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 22 },

  offer: {
    borderWidth: 1.5,
    borderColor: colors.brand,
    backgroundColor: colors.brandWash,
    borderRadius: radius.card,
    padding: 18,
  },
  offerTop: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  offerTitleRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  offerTitle: { flexShrink: 1, color: colors.ink, fontSize: 15, fontFamily: font.bold },
  offerSub: { color: colors.muted, fontSize: 12, fontFamily: font.regular, marginTop: 3 },
  offerReward: { color: colors.moneyText, fontSize: 22, fontFamily: font.black, letterSpacing: -0.6 },
  rewardLabel: { color: colors.mutedCool, fontSize: 10, fontFamily: font.regular },
  offerActions: { flexDirection: "row", gap: 10, marginTop: space.lg },
});
