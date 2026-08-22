import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useCallback } from "react";
import { Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { fetchNotifications, markAllRead } from "../src/api/notifications";
import {
  Body,
  Caption,
  Card,
  Divider,
  EmptyState,
  Hero,
  Loading,
  Row,
  Screen,
} from "../src/components/ui";
import { useSocket } from "../src/lib/ws";
import { colors, font, space, timeAgo } from "../src/theme";

/** Map notification types onto the same glyphs the rest of the app uses. */
const ICONS: Record<string, string> = {
  ORDER_ACCEPTED: "🤝",
  ORDER_PICKED_UP: "📦",
  ORDER_DELIVERED: "🎉",
  ORDER_COMPLETED: "✅",
  ORDER_CANCELLED: "🚫",
  ERRAND_EXPIRED: "😔",
  ERRAND_CANCELLED_BY_RUNNER: "😔",
  SETTLEMENT: "💰",
};

export default function Notifications() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ["notifications"],
    queryFn: fetchNotifications,
    refetchInterval: 60_000,
  });

  // Live pushes: the Kafka notification consumer writes the row, then fans it
  // out through Redis to this socket.
  useSocket(
    "/ws/notifications",
    useCallback(() => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }, [queryClient]),
  );

  const items = data?.items ?? [];

  return (
    <Screen
      scroll
      padded={false}
      tabBarClearance={false}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
      }
    >
      <Hero
        compact
        title="Notifications"
        subtitle={
          data?.unread ? `${data.unread} unread` : "Updates on your errands land here."
        }
      />

      <View style={{ paddingHorizontal: space.lg, paddingTop: space.lg }}>
        <Row justify="space-between" style={{ marginBottom: space.md }}>
          <Pressable onPress={() => router.back()} hitSlop={12}>
            <Caption style={{ fontFamily: font.bold, color: colors.brand }}>← Back</Caption>
          </Pressable>
          {data?.unread ? (
            <Pressable
              hitSlop={8}
              onPress={async () => {
                await markAllRead();
                queryClient.invalidateQueries({ queryKey: ["notifications"] });
              }}
            >
              <Caption style={{ fontFamily: font.bold, color: colors.brand }}>
                Mark all read
              </Caption>
            </Pressable>
          ) : null}
        </Row>

        {isLoading ? (
          <View style={{ height: 220 }}>
            <Loading />
          </View>
        ) : items.length === 0 ? (
          <EmptyState
            emoji="🔔"
            title="Nothing yet"
            body="When a runner accepts, picks up or delivers your errand, you'll hear about it here."
          />
        ) : (
          <Card raised style={{ padding: 0 }}>
            {items.map((n, i) => {
              const errandId = (n.data as { errand_id?: string } | null)?.errand_id;
              return (
                <View key={n.id}>
                  {i > 0 ? <Divider /> : null}
                  <Pressable
                    onPress={() => (errandId ? router.push(`/errand/${errandId}`) : undefined)}
                    style={({ pressed }) => [s.row, pressed && { backgroundColor: colors.bgSoft }]}
                  >
                    <View style={[s.iconWrap, !n.read_at && { backgroundColor: colors.brandSoft }]}>
                      <Text style={{ fontSize: 17 }}>{ICONS[n.type] ?? "🔔"}</Text>
                    </View>

                    <View style={{ flex: 1 }}>
                      <Body style={{ fontFamily: n.read_at ? font.regular : font.bold }}>
                        {n.title}
                      </Body>
                      {n.body ? (
                        <Caption style={{ marginTop: 2 }} numberOfLines={2}>
                          {n.body}
                        </Caption>
                      ) : null}
                    </View>

                    <View style={{ alignItems: "flex-end", gap: 5 }}>
                      <Caption style={{ fontSize: 10 }}>{timeAgo(n.created_at)}</Caption>
                      {!n.read_at ? <View style={s.dot} /> : null}
                    </View>
                  </Pressable>
                </View>
              );
            })}
          </Card>
        )}
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: "row", gap: space.md, alignItems: "flex-start", padding: space.lg },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.bgSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brand },
});
