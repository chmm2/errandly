import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import * as ImagePicker from "expo-image-picker";
import { useRouter } from "expo-router";
import { useState } from "react";
import { Image, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { fetchMe, setPhoto } from "../../src/api/auth";
import { type Errand, fetchMyErrands } from "../../src/api/errands";
import { fetchEarnings } from "../../src/api/ledger";
import { Icon, type IconName } from "../../src/components/icons";
import { PushStatus } from "../../src/components/PushStatus";
import { Footer, Hero, IconTile, Screen } from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { notify } from "../../src/lib/dialog";
import { unregisterForPush } from "../../src/lib/push";
import { useAuth } from "../../src/stores/auth";
import {
  categoryIcon,
  colors,
  font,
  radius,
  rupees,
  rupeesLong,
  shadow,
  space,
  statusStyle,
  timeAgo,
} from "../../src/theme";

const DONE = ["COMPLETED", "CANCELLED", "EXPIRED"];

/** Avatar render size is ~62pt; 512px covers the densest screens with room spare. */
const AVATAR_PX = 512;

/** A finished errand or run, in the compact history style. */
function HistoryRow({
  errand,
  onPress,
  first,
}: {
  errand: Errand;
  onPress: () => void;
  first: boolean;
}) {
  const status = statusStyle[errand.status];
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.histRow, !first && s.histDivider, pressed && s.pressed]}
    >
      <IconTile icon={categoryIcon[errand.category] ?? "gate"} size={36} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text numberOfLines={1} style={s.histTitle}>
          {errand.title}
        </Text>
        <Text numberOfLines={1} style={s.histSub}>
          {rupees(errand.reward)} reward, {timeAgo(errand.created_at)}
        </Text>
      </View>
      <Text style={[s.histStatus, { color: status.text }]}>{status.label}</Text>
    </Pressable>
  );
}

function StatBox({ value, label }: { value: string | number; label: string }) {
  return (
    <View style={s.statBox}>
      <Text style={s.stat}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

function SectionHead({ icon, title }: { icon: IconName; title: string }) {
  return (
    <View style={s.sectionHead}>
      <Icon name={icon} size={17} color={colors.brand} />
      <Text style={s.sectionTitle}>{title}</Text>
    </View>
  );
}

function History({
  items,
  empty,
  onOpen,
}: {
  items: Errand[];
  empty: string;
  onOpen: (id: string) => void;
}) {
  return (
    <View style={s.list}>
      {items.length === 0 ? (
        <View style={s.emptyInline}>
          <Text style={s.emptyText}>{empty}</Text>
        </View>
      ) : (
        items
          .slice(0, 5)
          .map((e, i) => (
            <HistoryRow key={e.id} errand={e} first={i === 0} onPress={() => onOpen(e.id)} />
          ))
      )}
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
  const spent = completedOrders.reduce(
    (sum, e) => sum + Number(e.reward) + Number(e.items_total),
    0,
  );

  const savePhoto = useMutation({
    mutationFn: (dataUrl: string | null) => setPhoto(dataUrl),
    onSuccess: async () => {
      setUser(await fetchMe());
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (err) => notify("Couldn't update photo", apiErrorMessage(err)),
  });

  /**
   * Pick a square avatar, shrink it, and send it as a data URL.
   *
   * The photo travels inside the JSON body as base64, which inflates it by a
   * third, so a straight-from-camera shot blows the field's 300k limit every
   * time. Downscaling first is what the web client does too: an avatar is never
   * rendered above ~64pt, so 512px is already generous.
   */
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
    });
    if (res.canceled || !res.assets[0]?.uri) return;

    setUploading(true);
    try {
      const context = ImageManipulator.manipulate(res.assets[0].uri);
      context.resize({ width: AVATAR_PX, height: AVATAR_PX });
      const rendered = await context.renderAsync();
      const out = await rendered.saveAsync({
        format: SaveFormat.JPEG,
        compress: 0.7,
        base64: true,
      });

      if (!out.base64) {
        notify("Couldn't read that image", "Try a different photo.");
        return;
      }
      await savePhoto.mutateAsync(`data:image/jpeg;base64,${out.base64}`);
    } catch (err) {
      notify("Couldn't update photo", apiErrorMessage(err, "That image couldn't be processed."));
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

  // No confirmation on log out: logging back in is a few taps, so a dialog is
  // pure friction. Cancelling an errand still confirms, that one can't be undone.

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
      <Hero title="Your profile" padBottom={60} />

      <View style={s.body}>
        {/* Identity, pulled up over the band */}
        <View style={[s.idCard, shadow.raised]}>
          <View style={s.idRow}>
            <Pressable
              onPress={pickPhoto}
              disabled={uploading}
              accessibilityRole="button"
              accessibilityLabel="Change profile photo"
            >
              <View style={s.avatar}>
                {user?.photo_url ? (
                  <Image source={{ uri: user.photo_url }} style={s.avatarImg} />
                ) : (
                  <Text style={s.initials}>{initials}</Text>
                )}
              </View>
              <View style={s.camera}>
                {uploading ? (
                  <Text style={s.cameraBusy}>…</Text>
                ) : (
                  <Icon name="camera" size={13} color={colors.brand} />
                )}
              </View>
            </Pressable>

            <View style={{ flex: 1, minWidth: 0 }}>
              <Text numberOfLines={1} style={s.name}>
                {user?.display_name ?? "—"}
              </Text>
              <Text numberOfLines={1} style={s.email}>
                {user?.email}
              </Text>
              <View style={s.badges}>
                <View style={[s.badge, { backgroundColor: colors.brandTint }]}>
                  <Icon name="star" size={12} color={colors.brand} />
                  <Text style={[s.badgeText, { color: colors.brand }]}>
                    {(user?.reputation_score ?? 5).toFixed(2)}
                  </Text>
                </View>
                {user?.account_status === "ACTIVE" ? (
                  <View style={[s.badge, { backgroundColor: colors.creditBg }]}>
                    <Icon name="shield" size={12} color={colors.credit} />
                    <Text style={[s.badgeText, { color: colors.credit }]}>Verified</Text>
                  </View>
                ) : null}
                {user?.student_id ? <Text style={s.studentId}>{user.student_id}</Text> : null}
              </View>
            </View>
          </View>
        </View>

        {/* Only renders when push is actually broken. */}
        <PushStatus />

        {/* ---------------------------------------------------- as a customer */}
        <SectionHead icon="order" title="As a customer" />
        <View style={s.stats}>
          <StatBox value={ordered.length} label="posted" />
          <StatBox value={completedOrders.length} label="completed" />
          <StatBox value={rupeesLong(spent)} label="spent" />
        </View>
        <History
          items={pastOrders}
          empty="Nothing finished yet. Your past errands will show up here."
          onOpen={(id) => router.push(`/errand/${id}`)}
        />

        {/* ------------------------------------------------------ as a runner */}
        <SectionHead icon="bike" title="As a runner" />
        <View style={s.stats}>
          <StatBox value={rupeesLong(earnings?.balance ?? 0)} label="balance" />
          <StatBox value={rupeesLong(earnings?.week_total ?? 0)} label="this week" />
          <StatBox value={earnings?.week_runs ?? 0} label="runs" />
        </View>
        <History
          items={pastRuns}
          empty="No completed runs yet. Accept an errand from the Run tab."
          onOpen={(id) => router.push(`/errand/${id}`)}
        />

        <Pressable
          onPress={async () => {
            // Drop this device first: once the token is gone the request
            // would be unauthenticated.
            await unregisterForPush();
            logout();
          }}
          style={({ pressed }) => [s.logout, pressed && s.pressed]}
          accessibilityRole="button"
        >
          <Icon name="logout" size={18} color={colors.caution} />
          <Text style={s.logoutText}>Log out</Text>
        </Pressable>

        <Footer />
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  body: { paddingHorizontal: 22, marginTop: -42 },
  pressed: { opacity: 0.7 },

  idCard: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.big,
    padding: 18,
  },
  idRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  avatar: {
    width: 62,
    height: 62,
    borderRadius: 31,
    backgroundColor: colors.brandTint,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  avatarImg: { width: "100%", height: "100%" },
  initials: { color: colors.brand, fontSize: 22, fontFamily: font.black },
  camera: {
    position: "absolute",
    right: -3,
    bottom: -3,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
    alignItems: "center",
    justifyContent: "center",
  },
  cameraBusy: { color: colors.brand, fontSize: 11, fontFamily: font.bold },
  name: { color: colors.ink, fontSize: 17, fontFamily: font.black, letterSpacing: -0.3 },
  email: { color: colors.muted, fontSize: 12, fontFamily: font.regular, marginTop: 1 },
  badges: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 8, marginTop: 6 },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  badgeText: { fontSize: 11, fontFamily: font.bold },
  studentId: { color: colors.mutedCool, fontSize: 11, fontFamily: font.mono },

  sectionHead: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: space.xl },
  sectionTitle: { color: colors.ink, fontSize: 15, fontFamily: font.black, letterSpacing: -0.3 },

  stats: { flexDirection: "row", gap: 10, marginTop: 10 },
  statBox: {
    flex: 1,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.xl,
    padding: 14,
  },
  stat: { color: colors.ink, fontSize: 20, fontFamily: font.black, letterSpacing: -0.5 },
  statLabel: { color: colors.muted, fontSize: 11, fontFamily: font.regular, marginTop: 1 },

  list: {
    marginTop: 14,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.xxl,
    overflow: "hidden",
  },
  histRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 15,
    paddingVertical: 13,
  },
  histDivider: { borderTopWidth: 1, borderTopColor: colors.hairlineSoft },
  histTitle: { color: colors.ink, fontSize: 13.5, fontFamily: font.semi },
  histSub: { color: colors.muted, fontSize: 11.5, fontFamily: font.regular },
  histStatus: { fontSize: 10.5, fontFamily: font.bold },
  emptyInline: { padding: space.xl, alignItems: "center" },
  emptyText: {
    color: colors.muted,
    fontSize: 12.5,
    fontFamily: font.regular,
    textAlign: "center",
    lineHeight: 19,
  },

  logout: {
    marginTop: space.lg,
    height: 48,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.cautionBorder,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  logoutText: { color: colors.caution, fontSize: 14, fontFamily: font.bold },
});
