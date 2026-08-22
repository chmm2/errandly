import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useCallback } from "react";
import { Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { type Category, type Errand, fetchMyErrands } from "../../src/api/errands";
import { ErrandCard } from "../../src/components/ErrandCard";
import {
  Body,
  Caption,
  EmptyState,
  Heading,
  Label,
  Loading,
  Row,
  Screen,
} from "../../src/components/ui";
import { useSocket } from "../../src/lib/ws";
import { useAuth } from "../../src/stores/auth";
import { categoryStyle, colors, font, radius, shadow, space } from "../../src/theme";

const LIVE: Errand["status"][] = ["OPEN", "ACCEPTED", "IN_PROGRESS", "DELIVERED"];
const QUICK: Category[] = ["FOOD", "GROCERY", "PARCEL", "STATIONERY", "PHARMACY", "CUSTOM"];

export default function Home() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuth((s) => s.user);

  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ["my-errands"],
    queryFn: fetchMyErrands,
    refetchInterval: 20_000, // fallback; the socket below is the fast path
  });

  const active = (data?.requested ?? []).filter((e) => LIVE.includes(e.status));
  const past = (data?.requested ?? []).filter((e) => !LIVE.includes(e.status));

  // One socket for the most recent live errand nudges the whole list to refetch.
  // (The backend publishes every transition to this errand's channel.)
  const watched = active[0]?.id ?? null;
  useSocket(
    watched ? `/ws/errands/${watched}` : null,
    useCallback(() => {
      queryClient.invalidateQueries({ queryKey: ["my-errands"] });
    }, [queryClient]),
  );

  const firstName = user?.display_name?.split(" ")[0] ?? "there";

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
      <View style={{ paddingTop: space.md }}>
        <Caption>Hey {firstName} 👋</Caption>
        <Heading style={{ marginTop: 2 }}>What do you need today?</Heading>
      </View>

      {/* Primary CTA */}
      <Pressable
        onPress={() => router.push("/errand/new")}
        style={({ pressed }) => [pressed && { opacity: 0.85, transform: [{ scale: 0.99 }] }]}
      >
        <LinearGradient
          colors={colors.brandGradient}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={[s.cta, shadow.glow(colors.brand)]}
        >
          <View style={{ flex: 1 }}>
            <Text style={s.ctaTitle}>Post an errand</Text>
            <Text style={s.ctaBody}>Someone nearby picks it up in minutes</Text>
          </View>
          <View style={s.ctaArrow}>
            <Text style={{ fontSize: 20, color: "#fff" }}>→</Text>
          </View>
        </LinearGradient>
      </Pressable>

      {/* Category quick-picks */}
      <Label style={{ marginTop: space.xl, marginBottom: space.sm }}>Quick start</Label>
      <Row gap={space.sm} wrap>
        {QUICK.map((c) => {
          const cat = categoryStyle[c];
          return (
            <Pressable
              key={c}
              onPress={() => router.push({ pathname: "/errand/new", params: { category: c } })}
              style={({ pressed }) => [
                s.quick,
                { borderColor: pressed ? cat.color : colors.border },
              ]}
            >
              <Text style={{ fontSize: 22 }}>{cat.emoji}</Text>
              <Caption style={{ color: colors.text, fontWeight: font.semi }}>{cat.label}</Caption>
            </Pressable>
          );
        })}
      </Row>

      {/* Active */}
      <Row justify="space-between" style={{ marginTop: space.xxl, marginBottom: space.sm }}>
        <Label>Your errands</Label>
        {active.length > 0 ? <Caption>{active.length} active</Caption> : null}
      </Row>

      {isLoading ? (
        <View style={{ height: 180 }}>
          <Loading />
        </View>
      ) : active.length === 0 && past.length === 0 ? (
        <View style={s.emptyBox}>
          <EmptyState
            emoji="🗒️"
            title="Nothing posted yet"
            body="Your errands will show up here once you post one."
          />
        </View>
      ) : (
        <View style={{ gap: space.md }}>
          {active.map((e) => (
            <ErrandCard key={e.id} errand={e} onPress={() => router.push(`/errand/${e.id}`)} />
          ))}

          {past.length > 0 ? (
            <>
              <Label style={{ marginTop: space.lg }}>Earlier</Label>
              {past.slice(0, 8).map((e) => (
                <ErrandCard key={e.id} errand={e} onPress={() => router.push(`/errand/${e.id}`)} />
              ))}
            </>
          ) : null}
        </View>
      )}

      {/* Running as a runner */}
      {(data?.running ?? []).length > 0 ? (
        <>
          <Label style={{ marginTop: space.xxl, marginBottom: space.sm }}>You're running</Label>
          <View style={{ gap: space.md }}>
            {data!.running.map((e) => (
              <ErrandCard key={e.id} errand={e} onPress={() => router.push(`/errand/${e.id}`)} />
            ))}
          </View>
        </>
      ) : null}
    </Screen>
  );
}

const s = StyleSheet.create({
  cta: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    borderRadius: radius.xl,
    padding: space.xl,
    marginTop: space.lg,
  },
  ctaTitle: { color: "#fff", fontSize: font.h2, fontWeight: font.black, letterSpacing: -0.3 },
  ctaBody: { color: "rgba(255,255,255,0.85)", fontSize: font.small, marginTop: 3 },
  ctaArrow: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: "rgba(255,255,255,0.22)",
    alignItems: "center",
    justifyContent: "center",
  },

  quick: {
    width: "31.5%",
    aspectRatio: 1.25,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
  },

  emptyBox: { height: 220, backgroundColor: colors.surface, borderRadius: radius.xl },
});
