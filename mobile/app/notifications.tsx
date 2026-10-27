import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useCallback } from "react";
import { Pressable, RefreshControl, StyleSheet, View } from "react-native";

import { fetchNotifications, markAllRead } from "../src/api/notifications";
import { Icon, type IconName } from "../src/components/icons";
import { Body, Caption, EmptyState, Hero, Screen, SkeletonRow } from "../src/components/ui";
import { useSocket } from "../src/lib/ws";
import { goBack } from "../src/lib/nav";
import { colors, font, radius, space, timeAgo } from "../src/theme";

/**
 * Notification types onto the same drawn glyphs the rest of the app uses, with
 * a tone per outcome: credit for things that went well, caution for things
 * that fell through, and the brand teal for progress in between.
 */
const ICONS: Record<string, { icon: IconName; fg: string; bg: string }> = {
  ORDER_ACCEPTED: { icon: "connects", fg: colors.brand, bg: colors.brandTint },
  ORDER_PICKED_UP: { icon: "bag", fg: colors.brand, bg: colors.brandTint },
  ORDER_DELIVERED: { icon: "check", fg: colors.credit, bg: colors.creditBg },
  ORDER_COMPLETED: { icon: "check", fg: colors.credit, bg: colors.creditBg },
  ORDER_CANCELLED: { icon: "close", fg: colors.caution, bg: colors.cautionBg },
  ERRAND_EXPIRED: { icon: "clock", fg: colors.caution, bg: colors.cautionBg },
  ERRAND_CANCELLED_BY_RUNNER: { icon: "close", fg: colors.caution, bg: colors.cautionBg },
  SETTLEMENT: { icon: "cash", fg: colors.credit, bg: colors.creditBg },
};
const FALLBACK = { icon: "bell" as IconName, fg: colors.brand, bg: colors.brandTint };

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
      edges={[]}
      bg={colors.bgSoft}
      tabBarClearance={false}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
      }
    >
      <Hero
        compact
        onBack={() => goBack(router)}
        title="Notifications"
        subtitle={
          data?.unread ? `${data.unread} unread` : "Updates on your errands land here."
        }
      />

      <View style={{ paddingHorizontal: 22, paddingTop: space.lg }}>
        <View style={s.toolbar}>
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
        </View>

        {isLoading ? (
          <View style={{ gap: space.sm }}>
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </View>
        ) : items.length === 0 ? (
          <EmptyState
            icon="bell"
            title="Nothing yet"
            body="When a runner accepts, picks up or delivers your errand, you'll hear about it here."
          />
        ) : (
          <View style={s.list}>
            {items.map((n, i) => {
              const errandId = (n.data as { errand_id?: string } | null)?.errand_id;
              const tone = ICONS[n.type] ?? FALLBACK;
              return (
                <View key={n.id}>
                  <Pressable
                    onPress={() => (errandId ? router.push(`/errand/${errandId}`) : undefined)}
                    style={({ pressed }) => [
                      s.row,
                      i > 0 && s.divider,
                      pressed && { backgroundColor: colors.bgSoft },
                    ]}
                  >
                    <View
                      style={[s.iconWrap, { backgroundColor: n.read_at ? colors.chip : tone.bg }]}
                    >
                      <Icon name={tone.icon} size={19} color={n.read_at ? colors.mutedCool : tone.fg} />
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
          </View>
        )}
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  toolbar: { flexDirection: "row", justifyContent: "flex-end", marginBottom: space.md, minHeight: 4 },
  list: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.xxl,
    overflow: "hidden",
  },
  row: { flexDirection: "row", gap: 12, alignItems: "flex-start", paddingHorizontal: 15, paddingVertical: 13 },
  divider: { borderTopWidth: 1, borderTopColor: colors.hairlineSoft },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    alignItems: "center",
    justifyContent: "center",
  },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brand },
});
