import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { useRouter } from "expo-router";
import { useState } from "react";
import { Image, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { fetchMe, setPhoto } from "../../src/api/auth";
import { type Errand, fetchMyErrands } from "../../src/api/errands";
import { fetchEarnings } from "../../src/api/ledger";
import {
  Body,
  Button,
  Caption,
  Card,
  Divider,
  Footer,
  Heading,
  Hero,
  IconTile,
  Row,
  Screen,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { confirm, notify } from "../../src/lib/dialog";
import { useAuth } from "../../src/stores/auth";
import {
  categoryIcon,
  colors,
  font,
  radius,
  rupees,
  space,
  statusStyle,
  timeAgo,
} from "../../src/theme";

const DONE = ["COMPLETED", "CANCELLED", "EXPIRED"];

/** A finished errand or run, in the compact history style. */
function HistoryRow({ errand, onPress }: { errand: Errand; onPress: () => void }) {
  const status = statusStyle[errand.status];
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.histRow, pressed && s.pressed]}>
      <IconTile emoji={categoryIcon[errand.category] ?? "✨"} size={38} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Body numberOfLines={1} style={{ fontFamily: font.semi }}>
          {errand.title}
        </Body>
        <Caption numberOfLines={1}>
          {rupees(errand.reward)} · {timeAgo(errand.created_at)}
        </Caption>
      </View>
      <Caption style={{ color: status.text, fontFamily: font.bold, fontSize: 10 }}>
        {status.label}
      </Caption>
    </Pressable>
  );
}

function StatBlock({ value, label }: { value: string | number; label: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={s.stat}>{value}</Text>
      <Caption>{label}</Caption>
    </View>
  );
}

export default function Profile() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setUser);
  const logout = useAuth((s) => s.logout);

  const [uploading, setUploading] = useState(false);

  const { data: earnings } = useQuery({ queryKey: ["earnings"], queryFn: fetchEarnings });
  const { data: mine, refetch, isRefetching } = useQuery({
    queryKey: ["my-errands"],
    queryFn: fetchMyErrands,
  });

  const ordered = mine?.requested ?? [];
  const ran = mine?.running ?? [];
  const pastOrders = ordered.filter((e) => DONE.includes(e.status));
  const pastRuns = ran.filter((e) => DONE.includes(e.status));
  const completedOrders = ordered.filter((e) => e.status === "COMPLETED");
  const spent = completedOrders.reduce((sum, e) => sum + Number(e.reward) + Number(e.items_total), 0);

  const savePhoto = useMutation({
    mutationFn: (dataUrl: string | null) => setPhoto(dataUrl),
    onSuccess: async () => {
      setUser(await fetchMe());
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (err) => notify("Couldn't update photo", apiErrorMessage(err)),
  });

  /** Pick a square avatar and send it as a data URL, matching the web client. */
  async function pickPhoto() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      notify("Permission needed", "Allow photo access to set a profile picture.");
      return;
    }
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.5,
      base64: true,
    });
    if (res.canceled || !res.assets[0]?.base64) return;

    setUploading(true);
    try {
      // The column caps at ~300k characters, so keep the payload small.
      const dataUrl = `data:image/jpeg;base64,${res.assets[0].base64}`;
      if (dataUrl.length > 290_000) {
        notify("Image too large", "Pick a smaller photo — try cropping it tighter.");
        return;
      }
      await savePhoto.mutateAsync(dataUrl);
    } finally {
      setUploading(false);
    }
  }

  const initials = (user?.display_name ?? "?")
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  async function confirmLogout() {
    const ok = await confirm("Log out?", "You'll need to log in again to post or run errands.", {
      confirmLabel: "Log out",
      destructive: true,
    });
    if (ok) logout();
  }

  return (
    <Screen
      scroll
      padded={false}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
      }
    >
      <Hero compact title="Your profile" />

      <View style={{ paddingHorizontal: space.lg }}>
        {/* Identity */}
        <Card raised style={s.idCard}>
          <Row gap={space.lg}>
            <Pressable onPress={pickPhoto} disabled={uploading}>
              <View style={s.avatar}>
                {user?.photo_url ? (
                  <Image source={{ uri: user.photo_url }} style={s.avatarImg} />
                ) : (
                  <Text style={s.initials}>{initials}</Text>
                )}
              </View>
              <View style={s.camera}>
                <Text style={{ fontSize: 11 }}>{uploading ? "…" : "📷"}</Text>
              </View>
            </Pressable>

            <View style={{ flex: 1 }}>
              <Body numberOfLines={1} style={{ fontFamily: font.black, fontSize: font.h3 }}>
                {user?.display_name ?? "—"}
              </Body>
              <Caption numberOfLines={1}>{user?.email}</Caption>
              <Row gap={space.sm} style={{ marginTop: 5 }} wrap>
                <Text style={s.stars}>★ {(user?.reputation_score ?? 5).toFixed(2)}</Text>
                {user?.student_id ? <Caption>· {user.student_id}</Caption> : null}
              </Row>
            </View>
          </Row>
          <Caption style={{ marginTop: space.md }}>Tap your photo to change it.</Caption>
        </Card>

        {/* ---------------------------------------------------- as a customer */}
        <Heading style={{ marginTop: space.xxl, marginBottom: space.md }}>🧑 As a customer</Heading>
        <Card raised>
          <Row gap={space.md}>
            <StatBlock value={ordered.length} label="errands posted" />
            <StatBlock value={completedOrders.length} label="completed" />
            <StatBlock value={rupees(spent)} label="total spent" />
          </Row>
        </Card>

        <Row justify="space-between" style={{ marginTop: space.lg, marginBottom: space.md }}>
          <Body style={{ fontFamily: font.bold }}>Previous errands</Body>
          {pastOrders.length > 5 ? <Caption>{pastOrders.length} total</Caption> : null}
        </Row>
        <Card raised style={{ padding: 0 }}>
          {pastOrders.length === 0 ? (
            <View style={s.emptyInline}>
              <Caption>Nothing finished yet — your past errands will show up here.</Caption>
            </View>
          ) : (
            pastOrders.slice(0, 5).map((e, i) => (
              <View key={e.id}>
                {i > 0 ? <Divider /> : null}
                <HistoryRow errand={e} onPress={() => router.push(`/errand/${e.id}`)} />
              </View>
            ))
          )}
        </Card>

        {/* ------------------------------------------------------ as a runner */}
        <Heading style={{ marginTop: space.xxl, marginBottom: space.md }}>🛵 As a runner</Heading>
        <Card raised>
          <Row gap={space.md}>
            <StatBlock value={rupees(earnings?.balance ?? 0)} label="balance" />
            <StatBlock value={rupees(earnings?.week_total ?? 0)} label="this week" />
            <StatBlock value={earnings?.week_runs ?? 0} label="runs this week" />
          </Row>
        </Card>

        <Row justify="space-between" style={{ marginTop: space.lg, marginBottom: space.md }}>
          <Body style={{ fontFamily: font.bold }}>Previous runs</Body>
          {pastRuns.length > 5 ? <Caption>{pastRuns.length} total</Caption> : null}
        </Row>
        <Card raised style={{ padding: 0 }}>
          {pastRuns.length === 0 ? (
            <View style={s.emptyInline}>
              <Caption>No completed runs yet — accept an errand from the Run tab.</Caption>
            </View>
          ) : (
            pastRuns.slice(0, 5).map((e, i) => (
              <View key={e.id}>
                {i > 0 ? <Divider /> : null}
                <HistoryRow errand={e} onPress={() => router.push(`/errand/${e.id}`)} />
              </View>
            ))
          )}
        </Card>

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
  pressed: { opacity: 0.7 },

  avatar: {
    width: 62,
    height: 62,
    borderRadius: 31,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  avatarImg: { width: "100%", height: "100%" },
  initials: { color: colors.brandDark, fontSize: 21, fontFamily: font.black },
  camera: {
    position: "absolute",
    right: -2,
    bottom: -2,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
    alignItems: "center",
    justifyContent: "center",
  },
  stars: { color: colors.brand, fontSize: font.small, fontFamily: font.bold },

  stat: { color: colors.ink, fontSize: font.h3, fontFamily: font.black },

  histRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.lg,
  },
  emptyInline: { padding: space.xl, alignItems: "center" },

  link: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    padding: space.lg,
  },
});
