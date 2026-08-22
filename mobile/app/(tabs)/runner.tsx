import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Location from "expo-location";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, RefreshControl, StyleSheet, Switch, Text, View } from "react-native";

import { fetchEarnings } from "../../src/api/ledger";
import { acceptErrand, type Errand, fetchFeed, fetchMyErrands } from "../../src/api/errands";
import { fetchRunnerProfile, setAvailability, updateLocation } from "../../src/api/runners";
import { ErrandCard } from "../../src/components/ErrandCard";
import {
  Body,
  Button,
  Caption,
  Card,
  EmptyState,
  Heading,
  Label,
  Loading,
  Row,
  Screen,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { useSocket } from "../../src/lib/ws";
import { colors, font, metres, radius, rupees, shadow, space } from "../../src/theme";

interface Offer {
  errand_id: string;
  title: string;
  category: string;
  reward: number;
  distance_m?: number;
}

/** Matches the web client's 10s send throttle. */
const LOCATION_SEND_MS = 10_000;

export default function Runner() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [geo, setGeo] = useState<{ lat: number; lng: number } | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [toggling, setToggling] = useState(false);
  const lastSent = useRef(0);

  const { data: profile } = useQuery({
    queryKey: ["runner-profile"],
    queryFn: fetchRunnerProfile,
  });
  const available = profile?.is_available ?? false;

  const { data: earnings } = useQuery({ queryKey: ["earnings"], queryFn: fetchEarnings });

  const { data: feed, refetch, isRefetching } = useQuery({
    queryKey: ["runner-feed", geo?.lat, geo?.lng],
    queryFn: () => fetchFeed(20, 0, geo ?? undefined),
    enabled: available,
    refetchInterval: 20_000,
  });

  const { data: mine } = useQuery({ queryKey: ["my-errands"], queryFn: fetchMyErrands });
  const activeRuns = (mine?.running ?? []).filter((e) =>
    ["ACCEPTED", "IN_PROGRESS", "DELIVERED"].includes(e.status),
  );

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

  /* ---- go online / offline ------------------------------------------ */
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
            "Errandly matches you with errands near you, so runner mode needs location access.",
          );
          return;
        }
        const pos = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.High,
        });
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

  const nearby = (feed?.items ?? []).filter(
    (e) => !activeRuns.some((r) => r.id === e.id),
  );

  return (
    <Screen
      scroll
      refreshControl={
        <RefreshControl
          refreshing={isRefetching}
          onRefresh={refetch}
          tintColor={colors.brandBright}
        />
      }
    >
      <Heading style={{ paddingTop: space.md }}>Runner mode</Heading>

      {/* Online switch + earnings */}
      <Card style={{ marginTop: space.lg, overflow: "hidden" }} glow={available ? colors.success : undefined}>
        {available ? (
          <LinearGradient
            colors={["rgba(47,217,143,0.14)", "transparent"]}
            style={StyleSheet.absoluteFill}
          />
        ) : null}
        <Row justify="space-between">
          <View style={{ flex: 1 }}>
            <Row gap={space.sm}>
              <View style={[s.dot, { backgroundColor: available ? colors.success : colors.textFaint }]} />
              <Body style={{ fontWeight: font.bold }}>
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
            trackColor={{ false: colors.surfacePressed, true: "rgba(47,217,143,0.5)" }}
            thumbColor={available ? colors.success : colors.textFaint}
          />
        </Row>

        <Row gap={space.xl} style={s.stats}>
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
          <Label style={{ marginTop: space.xl, marginBottom: space.sm }}>
            ⚡ Live offers for you
          </Label>
          <View style={{ gap: space.sm }}>
            {offers.map((o) => (
              <Card key={o.errand_id} style={s.offer} glow={colors.brand}>
                <Row justify="space-between" gap={space.md}>
                  <View style={{ flex: 1 }}>
                    <Body numberOfLines={1} style={{ fontWeight: font.bold }}>
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
                    size="md"
                    loading={accept.isPending}
                    onPress={() => accept.mutate(o.errand_id)}
                    style={{ flex: 1 }}
                  />
                  <Button
                    title="Skip"
                    variant="surface"
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
          <Label style={{ marginTop: space.xl, marginBottom: space.sm }}>Your active runs</Label>
          <View style={{ gap: space.md }}>
            {activeRuns.map((e) => (
              <ErrandCard key={e.id} errand={e} onPress={() => router.push(`/errand/${e.id}`)} />
            ))}
          </View>
        </>
      ) : null}

      {/* Nearby feed */}
      <Label style={{ marginTop: space.xl, marginBottom: space.sm }}>Nearby errands</Label>
      {!available ? (
        <Card style={s.offlineBox}>
          <EmptyState
            emoji="🛵"
            title="You're offline"
            body="Flip the switch above to see errands around you and get live offers."
          />
        </Card>
      ) : nearby.length === 0 ? (
        <Card style={s.offlineBox}>
          <EmptyState
            emoji="🌙"
            title="Nothing nearby yet"
            body="New errands appear here the moment someone posts one."
          />
        </Card>
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
    </Screen>
  );
}

const s = StyleSheet.create({
  dot: { width: 9, height: 9, borderRadius: 5 },
  stats: {
    marginTop: space.lg,
    paddingTop: space.lg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  statValue: { color: colors.text, fontSize: font.h3, fontWeight: font.black },

  offer: { borderColor: colors.brandDeep, backgroundColor: colors.surfaceHigh },
  offerReward: { color: colors.gold, fontSize: font.h2, fontWeight: font.black },

  offlineBox: { height: 230, padding: 0, justifyContent: "center" },
});
