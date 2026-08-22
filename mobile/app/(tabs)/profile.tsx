import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";

import { fetchEarnings } from "../../src/api/ledger";
import { fetchNotifications, markAllRead } from "../../src/api/notifications";
import { BackendSetting } from "../../src/components/BackendSetting";
import {
  Body,
  Button,
  Caption,
  Card,
  Divider,
  Footer,
  Heading,
  Hero,
  Row,
  Screen,
} from "../../src/components/ui";
import { useSocket } from "../../src/lib/ws";
import { useAuth } from "../../src/stores/auth";
import { colors, font, radius, rupees, space, timeAgo } from "../../src/theme";

export default function Profile() {
  const queryClient = useQueryClient();
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);

  const { data: earnings } = useQuery({ queryKey: ["earnings"], queryFn: fetchEarnings });
  const { data: notifications } = useQuery({
    queryKey: ["notifications"],
    queryFn: fetchNotifications,
    refetchInterval: 60_000,
  });

  // Live notification pushes (Kafka consumer -> Redis -> this socket).
  useSocket(
    "/ws/notifications",
    useCallback(() => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }, [queryClient]),
  );

  const initials = (user?.display_name ?? "?")
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  function confirmLogout() {
    Alert.alert("Log out?", "You'll need to log in again to post or run errands.", [
      { text: "Cancel", style: "cancel" },
      { text: "Log out", style: "destructive", onPress: logout },
    ]);
  }

  return (
    <Screen scroll padded={false}>
      <Hero compact title="Your profile" />

      <View style={{ paddingHorizontal: space.lg }}>
        {/* Identity card, pulled up over the hero edge */}
        <Card raised style={s.idCard}>
          <Row gap={space.lg}>
            <View style={s.avatar}>
              <Text style={s.initials}>{initials}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Body numberOfLines={1} style={{ fontFamily: font.black, fontSize: font.h3 }}>
                {user?.display_name ?? "—"}
              </Body>
              <Caption numberOfLines={1}>{user?.email}</Caption>
              <Row gap={space.sm} style={{ marginTop: 5 }}>
                <Text style={s.stars}>★ {(user?.reputation_score ?? 5).toFixed(2)}</Text>
                {user?.student_id ? <Caption>· {user.student_id}</Caption> : null}
              </Row>
            </View>
          </Row>
        </Card>

        {/* Earnings */}
        <Heading style={{ marginTop: space.xxl, marginBottom: space.md }}>Earnings</Heading>
        <Card raised>
          <Row gap={space.xxl}>
            <View>
              <Text style={s.big}>{rupees(earnings?.balance ?? 0)}</Text>
              <Caption>balance</Caption>
            </View>
            <View>
              <Text style={s.big}>{rupees(earnings?.week_total ?? 0)}</Text>
              <Caption>this week</Caption>
            </View>
            <View>
              <Text style={s.big}>{earnings?.week_runs ?? 0}</Text>
              <Caption>runs</Caption>
            </View>
          </Row>
        </Card>

        {/* Notifications */}
        <Row justify="space-between" style={{ marginTop: space.xxl, marginBottom: space.md }}>
          <Heading>
            Notifications{notifications?.unread ? ` · ${notifications.unread}` : ""}
          </Heading>
          {notifications?.unread ? (
            <Pressable
              hitSlop={8}
              onPress={async () => {
                await markAllRead();
                queryClient.invalidateQueries({ queryKey: ["notifications"] });
              }}
            >
              <Text style={s.link}>Mark all read</Text>
            </Pressable>
          ) : null}
        </Row>

        <Card raised style={{ padding: 0 }}>
          {(notifications?.items ?? []).length === 0 ? (
            <View style={{ padding: space.xxl, alignItems: "center" }}>
              <Text style={{ fontSize: 26, marginBottom: space.sm }}>🔔</Text>
              <Caption>Nothing yet — updates land here live.</Caption>
            </View>
          ) : (
            notifications!.items.slice(0, 12).map((n, i) => (
              <View key={n.id}>
                {i > 0 ? <Divider /> : null}
                <View style={s.notif}>
                  <View style={[s.unreadDot, { opacity: n.read_at ? 0 : 1 }]} />
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
                  <Caption>{timeAgo(n.created_at)}</Caption>
                </View>
              </View>
            ))
          )}
        </Card>

        {/* Server address — editable so a moved backend doesn't need a rebuild */}
        <Heading style={{ marginTop: space.xxl, marginBottom: space.md }}>Server</Heading>
        <BackendSetting />

        <Button
          title="Log out"
          variant="outline"
          onPress={confirmLogout}
          style={{ marginTop: space.xxl }}
        />

        <Footer />
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  idCard: { marginTop: -space.xl },
  avatar: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  initials: { color: colors.brandDark, fontSize: 21, fontFamily: font.black },
  stars: { color: colors.brand, fontSize: font.small, fontFamily: font.bold },

  big: { color: colors.ink, fontSize: font.h2, fontFamily: font.black },
  link: { color: colors.brand, fontSize: font.small, fontFamily: font.bold },

  notif: { flexDirection: "row", gap: space.md, alignItems: "flex-start", padding: space.lg },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.brand,
    marginTop: 6,
  },
});
