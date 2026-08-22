import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Location from "expo-location";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, RefreshControl, StyleSheet, Switch, Text, View } from "react-native";

import { acceptErrand, type Errand, fetchFeed, fetchMyErrands } from "../../src/api/errands";
import { fetchEarnings } from "../../src/api/ledger";
import { fetchRunnerProfile, setAvailability, updateLocation } from "../../src/api/runners";
import { ErrandCard } from "../../src/components/ErrandCard";
import {
  Body,
  Button,
  Caption,
  Card,
  EmptyState,
  Heading,
  Hero,
  Loading,
  Row,
  Screen,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { useSocket } from "../../src/lib/ws";
import { colors, font, metres, radius, rupees, space } from "../../src/theme";

interface Offer {
  errand_id: string;
  title: string;
  category: string;
  reward: number;
  distance_m?: number;
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
          Alert.alert(
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
      Alert.alert("Couldn't update", apiErrorMessage(err));
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
    onError: (err) => Alert.alert("Couldn't accept", apiErrorMessage(err)),
  });

  const nearby = (feed?.items ?? []).filter((e) => !activeRuns.some((r) => r.id === e.id));

  return (
    <Screen
      scroll
      padded={false}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
      }
    >
      <Hero
        compact
        title="Run mode 🛵"
        subtitle="Pick up an errand on your way back to the hostel and earn for the trip you were making anyway."
      />

      <View style={{ paddingHorizontal: space.lg, paddingTop: space.xl }}>
        {/* Online switch + earnings */}
        <Card raised>
          <Row justify="space-between">
            <View style={{ flex: 1 }}>
              <Row gap={space.sm}>
                <View
                  style={[s.dot, { backgroundColor: available ? colors.emerald : colors.muted }]}
                />
                <Body style={{ fontFamily: font.bold }}>
                  {available ? "You're online" : "You're offline"}
                </Body>
              </Row>
              <Caption style={{ marginTop: 3 }}>
                {available
                  ? "Nearby errands will ping you instantly."
                  : "Go online to start receiving offers."}
              </Caption>
            </View>
            <Switch
              value={available}
              onValueChange={toggle}
              disabled={toggling}
              trackColor={{ false: colors.line, true: colors.brandSoft }}
              thumbColor={available ? colors.brand : "#f4f4f5"}
            />
          </Row>

          <Row gap={space.xxl} style={s.stats}>
            <View>
              <Text style={s.statValue}>{rupees(earnings?.balance ?? 0)}</Text>
              <Caption>balance</Caption>
            </View>
            <View>
              <Text style={s.statValue}>{rupees(earnings?.week_total ?? 0)}</Text>
              <Caption>this week</Caption>
            </View>
            <View>
              <Text style={s.statValue}>{earnings?.week_runs ?? 0}</Text>
              <Caption>runs</Caption>
            </View>
          </Row>
        </Card>

        {/* Live offers */}
        {offers.length > 0 ? (
          <>
            <Heading style={{ marginTop: space.xxl }}>⚡ Live offers for you</Heading>
            <View style={{ gap: space.md, marginTop: space.lg }}>
              {offers.map((o) => (
                <Card key={o.errand_id} raised style={s.offer}>
                  <Row justify="space-between" gap={space.md}>
                    <View style={{ flex: 1 }}>
                      <Body numberOfLines={1} style={{ fontFamily: font.bold }}>
                        {o.title}
                      </Body>
                      <Caption style={{ marginTop: 2 }}>
                        {o.distance_m != null ? `${metres(o.distance_m)} away` : "Nearby"}
                      </Caption>
                    </View>
                    <Text style={s.offerReward}>{rupees(o.reward)}</Text>
                  </Row>
                  <Row gap={space.sm} style={{ marginTop: space.md }}>
                    <Button
                      title="Accept"
                      loading={accept.isPending}
                      onPress={() => accept.mutate(o.errand_id)}
                      style={{ flex: 1 }}
                    />
                    <Button
                      title="Skip"
                      variant="outline"
                      onPress={() =>
                        setOffers((prev) => prev.filter((x) => x.errand_id !== o.errand_id))
                      }
                      style={{ flex: 1 }}
                    />
                  </Row>
                </Card>
              ))}
            </View>
          </>
        ) : null}

        {/* Active runs */}
        {activeRuns.length > 0 ? (
          <>
            <Heading style={{ marginTop: space.xxl }}>Your active runs</Heading>
            <View style={{ gap: space.md, marginTop: space.lg }}>
              {activeRuns.map((e) => (
                <ErrandCard key={e.id} errand={e} onPress={() => router.push(`/errand/${e.id}`)} />
              ))}
            </View>
          </>
        ) : null}

        {/* Nearby feed */}
        <Heading style={{ marginTop: space.xxl, marginBottom: space.lg }}>Nearby errands</Heading>
        {!available ? (
          <EmptyState
            emoji="🛵"
            title="You're offline"
            body="Flip the switch above to see errands around you and get live offers."
          />
        ) : nearby.length === 0 ? (
          <EmptyState
            emoji="🌙"
            title="Nothing nearby yet"
            body="New errands appear here the moment someone posts one."
          />
        ) : (
          <View style={{ gap: space.md }}>
            {nearby.map((e: Errand) => (
              <ErrandCard
                key={e.id}
                errand={e}
                showStatus={false}
                onPress={() => router.push(`/errand/${e.id}`)}
                footer={
                  <Button
                    title="Accept this run"
                    loading={accept.isPending && accept.variables === e.id}
                    onPress={() => accept.mutate(e.id)}
                  />
                }
              />
            ))}
          </View>
        )}
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  dot: { width: 9, height: 9, borderRadius: 5 },
  stats: {
    marginTop: space.lg,
    paddingTop: space.lg,
    borderTopWidth: 1,
    borderTopColor: colors.line,
  },
  statValue: { color: colors.ink, fontSize: font.h3, fontFamily: font.black },

  offer: { borderColor: colors.brand, backgroundColor: colors.brandSoft },
  offerReward: { color: colors.brand, fontSize: font.h2, fontFamily: font.black },
});
