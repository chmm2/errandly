import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Location from "expo-location";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useMemo, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";

import { createErrand } from "../../src/api/errands";
import { fetchMenu, type MenuItem } from "../../src/api/vendors";
import {
  Body,
  Button,
  Caption,
  Card,
  Chip,
  Divider,
  Heading,
  Label,
  Loading,
  Row,
  Screen,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { categoryStyle, colors, font, radius, rupees, shadow, space } from "../../src/theme";

const DEFAULT_REWARD = 20;

export default function VendorMenu() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [cart, setCart] = useState<Record<string, number>>({});
  const [posting, setPosting] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["menu", id],
    queryFn: () => fetchMenu(id!),
    enabled: !!id,
    refetchInterval: 30_000, // sold-out states move fast at a canteen
  });

  /** Menu grouped into its sections, preserving the backend's ordering. */
  const sections = useMemo(() => {
    const out: Record<string, MenuItem[]> = {};
    for (const item of data?.items ?? []) {
      (out[item.section] ??= []).push(item);
    }
    return Object.entries(out);
  }, [data]);

  const lines = Object.entries(cart).filter(([, qty]) => qty > 0);
  const total = lines.reduce((sum, [itemId, qty]) => {
    const item = data?.items.find((i) => i.id === itemId);
    return sum + (item?.price ?? 0) * qty;
  }, 0);

  const bump = (itemId: string, delta: number) =>
    setCart((c) => {
      const next = Math.max(0, (c[itemId] ?? 0) + delta);
      return { ...c, [itemId]: next };
    });

  const post = useMutation({
    mutationFn: createErrand,
    onSuccess: (errand) => {
      queryClient.invalidateQueries({ queryKey: ["my-errands"] });
      router.replace(`/errand/${errand.id}`);
    },
    onError: (err) => Alert.alert("Couldn't post order", apiErrorMessage(err)),
  });

  async function checkout() {
    if (!data || lines.length === 0) return;
    setPosting(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") {
        Alert.alert("Location needed", "We need your location so the runner knows where to deliver.");
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });

      post.mutate({
        category: data.vendor.category,
        vendor_id: data.vendor.id,
        items: lines.map(([menu_item_id, quantity]) => ({ menu_item_id, quantity })),
        title: `${lines.reduce((n, [, q]) => n + q, 0)} items from ${data.vendor.name}`,
        pickup_label: data.vendor.name,
        drop_lat: pos.coords.latitude,
        drop_lng: pos.coords.longitude,
        reward: DEFAULT_REWARD,
        wait_minutes: 30,
      });
    } finally {
      setPosting(false);
    }
  }

  if (isLoading || !data) {
    return (
      <Screen>
        <Loading label="Loading menu…" />
      </Screen>
    );
  }

  const cat = categoryStyle[data.vendor.category];

  return (
    <Screen padded={false}>
      <View style={{ flex: 1 }}>
        <Screen scroll edges={[]}>
          <Row justify="space-between" style={{ paddingTop: space.md }}>
            <Pressable onPress={() => router.back()} style={s.back} hitSlop={12}>
              <Text style={s.backGlyph}>←</Text>
            </Pressable>
            <Chip
              label={data.vendor.is_open ? "Open now" : "Closed"}
              color={data.vendor.is_open ? colors.success : colors.textFaint}
              tint={data.vendor.is_open ? "rgba(47,217,143,0.14)" : colors.surfaceHigh}
            />
          </Row>

          <Row gap={space.md} style={{ marginTop: space.lg }}>
            <View style={[s.avatar, { backgroundColor: cat.tint }]}>
              <Text style={{ fontSize: 26 }}>{cat.emoji}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Heading>{data.vendor.name}</Heading>
              {data.vendor.description ? (
                <Caption style={{ marginTop: 2 }}>{data.vendor.description}</Caption>
              ) : null}
            </View>
          </Row>

          {data.stale ? (
            <Card style={s.staleCard}>
              <Caption style={{ color: colors.warning }}>
                ⚠️ Showing a slightly older menu — live prices couldn't be reached.
              </Caption>
            </Card>
          ) : null}

          {!data.vendor.is_open ? (
            <Card style={{ marginTop: space.lg }}>
              <Caption>This store is closed right now, so orders can't be placed.</Caption>
            </Card>
          ) : null}

          {sections.map(([section, items]) => (
            <View key={section} style={{ marginTop: space.xl }}>
              <Label style={{ marginBottom: space.sm }}>{section}</Label>
              <Card style={{ padding: 0 }}>
                {items.map((item, i) => {
                  const qty = cart[item.id] ?? 0;
                  return (
                    <View key={item.id}>
                      {i > 0 ? <Divider /> : null}
                      <Row justify="space-between" gap={space.md} style={{ padding: space.lg }}>
                        <View style={{ flex: 1 }}>
                          <Body
                            style={{
                              fontWeight: font.semi,
                              color: item.is_available ? colors.text : colors.textFaint,
                            }}
                          >
                            {item.name}
                          </Body>
                          <Caption style={{ marginTop: 2, color: colors.gold }}>
                            {rupees(item.price)}
                          </Caption>
                          {!item.is_available ? (
                            <Caption style={{ color: colors.danger }}>Sold out</Caption>
                          ) : null}
                        </View>

                        {item.is_available && data.vendor.is_open ? (
                          qty > 0 ? (
                            <Row gap={space.sm}>
                              <Pressable onPress={() => bump(item.id, -1)} style={s.step}>
                                <Text style={s.stepGlyph}>−</Text>
                              </Pressable>
                              <Text style={s.qty}>{qty}</Text>
                              <Pressable onPress={() => bump(item.id, 1)} style={s.step}>
                                <Text style={s.stepGlyph}>+</Text>
                              </Pressable>
                            </Row>
                          ) : (
                            <Pressable onPress={() => bump(item.id, 1)} style={s.add}>
                              <Text style={s.addText}>Add</Text>
                            </Pressable>
                          )
                        ) : null}
                      </Row>
                    </View>
                  );
                })}
              </Card>
            </View>
          ))}
        </Screen>

        {/* Sticky cart bar */}
        {lines.length > 0 ? (
          <View style={[s.cartBar, shadow.raised]}>
            <LinearGradient
              colors={colors.brandGradient}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={StyleSheet.absoluteFill}
            />
            <Row justify="space-between" gap={space.md}>
              <View>
                <Text style={s.cartCount}>
                  {lines.reduce((n, [, q]) => n + q, 0)} items · {rupees(total)}
                </Text>
                <Text style={s.cartHint}>+ {rupees(DEFAULT_REWARD)} runner reward</Text>
              </View>
              <Pressable
                onPress={checkout}
                disabled={post.isPending || posting}
                style={s.cartBtn}
              >
                <Text style={s.cartBtnText}>
                  {post.isPending || posting ? "Posting…" : "Post errand"}
                </Text>
              </Pressable>
            </Row>
          </View>
        ) : null}
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  back: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surfaceHigh,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  backGlyph: { color: colors.text, fontSize: 19, fontWeight: font.bold },

  avatar: {
    width: 62,
    height: 62,
    borderRadius: radius.lg,
    alignItems: "center",
    justifyContent: "center",
  },

  staleCard: {
    marginTop: space.lg,
    backgroundColor: "rgba(255,176,32,0.08)",
    borderColor: "rgba(255,176,32,0.4)",
  },

  add: {
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.brand,
    backgroundColor: "rgba(124,92,255,0.14)",
  },
  addText: { color: colors.brandBright, fontSize: font.small, fontWeight: font.bold },

  step: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.surfaceHigh,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  stepGlyph: { color: colors.text, fontSize: 17, fontWeight: font.bold },
  qty: { color: colors.text, fontSize: font.body, fontWeight: font.bold, minWidth: 18, textAlign: "center" },

  cartBar: {
    position: "absolute",
    left: space.lg,
    right: space.lg,
    bottom: space.xl,
    borderRadius: radius.xl,
    padding: space.lg,
    overflow: "hidden",
  },
  cartCount: { color: "#fff", fontSize: font.h3, fontWeight: font.black },
  cartHint: { color: "rgba(255,255,255,0.82)", fontSize: font.tiny, marginTop: 1 },
  cartBtn: {
    paddingHorizontal: space.lg,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: "rgba(255,255,255,0.22)",
    alignItems: "center",
    justifyContent: "center",
  },
  cartBtnText: { color: "#fff", fontSize: font.body, fontWeight: font.bold },
});
