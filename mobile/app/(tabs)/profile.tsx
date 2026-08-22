import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LinearGradient } from "expo-linear-gradient";
import { useCallback } from "react";
import { Alert, StyleSheet, Text, View } from "react-native";

import { fetchEarnings } from "../../src/api/ledger";
import { fetchNotifications, markAllRead } from "../../src/api/notifications";
import { BackendSetting } from "../../src/components/BackendSetting";
import {
  Body,
  Button,
  Caption,
  Card,
  Divider,
  Heading,
  Label,
  Row,
  Screen,
} from "../../src/components/ui";
import { useSocket } from "../../src/lib/ws";
import { useAuth } from "../../src/stores/auth";
import { colors, font, rupees, shadow, space, timeAgo } from "../../src/theme";

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
    Alert.alert("Sign out?", "You'll need to sign in again to post or run errands.", [
      { text: "Cancel", style: "cancel" },
      { text: "Sign out", style: "destructive", onPress: logout },
    ]);
  }

  return (
    <Screen scroll>
      {/* Identity header */}
      <LinearGradient
        colors={["rgba(124,92,255,0.28)", "transparent"]}
        style={s.headerWash}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
      />

      <Row gap={space.lg} style={{ paddingTop: space.xl }}>
        <View style={[s.avatar, shadow.glow(colors.brand)]}>
          <LinearGradient
            colors={colors.brandGradient}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={[StyleSheet.absoluteFill, { borderRadius: 34 }]}
          />
          <Text style={s.initials}>{initials}</Text>
        </View>

        <View style={{ flex: 1 }}>
          <Heading numberOfLines={1}>{user?.display_name ?? "—"}</Heading>
          <Caption numberOfLines={1}>{user?.email}</Caption>
          <Row gap={space.sm} style={{ marginTop: space.sm }}>
            <Text style={s.stars}>
              ⭐ {(user?.reputation_score ?? 5).toFixed(2)}
            </Text>
            {user?.student_id ? <Caption>· {user.student_id}</Caption> : null}
          </Row>
        </View>
      </Row>

      {/* Earnings */}
      <Card style={{ marginTop: space.xl }}>
        <Label>Earnings</Label>
        <Row gap={space.xl} style={{ marginTop: space.md }}>
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
      <Row justify="space-between" style={{ marginTop: space.xxl, marginBottom: space.sm }}>
        <Label>
          Notifications{notifications?.unread ? ` · ${notifications.unread} new` : ""}
        </Label>
        {notifications?.unread ? (
          <Text
            style={s.link}
            onPress={async () => {
              await markAllRead();
              queryClient.invalidateQueries({ queryKey: ["notifications"] });
            }}
          >
            Mark all read
          </Text>
        ) : null}
      </Row>

      <Card style={{ padding: 0 }}>
        {(notifications?.items ?? []).length === 0 ? (
          <View style={{ padding: space.xl, alignItems: "center" }}>
            <Text style={{ fontSize: 28, marginBottom: space.sm }}>🔔</Text>
            <Caption>Nothing yet — updates land here live.</Caption>
          </View>
        ) : (
          notifications!.items.slice(0, 12).map((n, i) => (
            <View key={n.id}>
              {i > 0 ? <Divider /> : null}
              <View style={s.notif}>
                <View style={[s.unreadDot, { opacity: n.read_at ? 0 : 1 }]} />
                <View style={{ flex: 1 }}>
                  <Body style={{ fontWeight: n.read_at ? font.regular : font.bold }}>
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

      {/* Backend address — editable, because a release build otherwise has it
          frozen in and any tunnel change would need a full rebuild. */}
      <Label style={{ marginTop: space.xxl, marginBottom: space.sm }}>Backend</Label>
      <BackendSetting />

      <Button
        title="Sign out"
        variant="danger"
        onPress={confirmLogout}
        style={{ marginTop: space.xxl }}
      />
    </Screen>
  );
}

const s = StyleSheet.create({
  headerWash: { position: "absolute", top: 0, left: 0, right: 0, height: 200 },
  avatar: {
    width: 68,
    height: 68,
    borderRadius: 34,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  initials: { color: "#fff", fontSize: 24, fontWeight: font.black, letterSpacing: 0.5 },
  stars: { color: colors.gold, fontSize: font.small, fontWeight: font.bold },

  big: { color: colors.text, fontSize: font.h2, fontWeight: font.black },
  link: { color: colors.brandBright, fontSize: font.small, fontWeight: font.bold },

  notif: { flexDirection: "row", gap: space.md, alignItems: "flex-start", padding: space.lg },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.brandBright,
    marginTop: 6,
  },
});
