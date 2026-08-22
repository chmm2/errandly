import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Location from "expo-location";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useMemo, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";

import { createErrand } from "../../src/api/errands";
import { fetchMenu, type MenuItem } from "../../src/api/vendors";
import {
  Body,
  Caption,
  Card,
  Divider,
  Heading,
  Hero,
  Loading,
  Pill,
  Row,
  Screen,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { colors, font, radius, rupees, shadow, space } from "../../src/theme";

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
  const count = lines.reduce((n, [, q]) => n + q, 0);

  const bump = (itemId: string, delta: number) =>
    setCart((c) => ({ ...c, [itemId]: Math.max(0, (c[itemId] ?? 0) + delta) }));

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
        Alert.alert("Location needed", "We need your location so the runner knows where to bring it.");
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });

      post.mutate({
        category: data.vendor.category,
        vendor_id: data.vendor.id,
        items: lines.map(([menu_item_id, quantity]) => ({ menu_item_id, quantity })),
        title: `${count} item${count > 1 ? "s" : ""} from ${data.vendor.name}`,
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

  return (
    <Screen padded={false}>
      <View style={{ flex: 1 }}>
        <Screen scroll padded={false} edges={[]}>
          <Hero compact title={data.vendor.name} subtitle={data.vendor.description ?? undefined}>
            <View style={{ marginTop: space.md, alignSelf: "flex-start" }}>
              <Pill
                label={data.vendor.is_open ? "● Open now" : "Closed"}
                bg={data.vendor.is_open ? "rgba(255,255,255,0.22)" : colors.grayBg}
                color={data.vendor.is_open ? colors.white : colors.muted}
              />
            </View>
          </Hero>

          <View style={{ paddingHorizontal: space.lg, paddingTop: space.lg }}>
            <Pressable onPress={() => router.back()} hitSlop={12}>
              <Caption style={{ fontFamily: font.bold, color: colors.brand }}>← Back</Caption>
            </Pressable>

            {data.stale ? (
              <Card style={s.stale}>
                <Caption style={{ color: colors.amberText }}>
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
              <View key={section} style={{ marginTop: space.xxl }}>
                <Heading style={{ marginBottom: space.md }}>{section}</Heading>
                <Card raised style={{ padding: 0 }}>
                  {items.map((item, i) => {
                    const qty = cart[item.id] ?? 0;
                    return (
                      <View key={item.id}>
                        {i > 0 ? <Divider /> : null}
                        <Row justify="space-between" gap={space.md} style={{ padding: space.lg }}>
                          <View style={{ flex: 1 }}>
                            <Body
                              style={{
                                fontFamily: font.semi,
                                color: item.is_available ? colors.ink : colors.muted,
                              }}
                            >
                              {item.name}
                            </Body>
                            <Caption style={{ marginTop: 2, color: colors.brand, fontFamily: font.bold }}>
                              {rupees(item.price)}
                            </Caption>
                            {!item.is_available ? (
                              <Caption style={{ color: colors.redText }}>Sold out</Caption>
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
                                <Text style={s.addText}>ADD</Text>
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
          </View>
        </Screen>

        {/* Sticky cart bar */}
        {lines.length > 0 ? (
          <View style={[s.cartBar, shadow.raised]}>
            <Row justify="space-between" gap={space.md}>
              <View>
                <Text style={s.cartCount}>
                  {count} item{count > 1 ? "s" : ""} · {rupees(total)}
                </Text>
                <Text style={s.cartHint}>+ {rupees(DEFAULT_REWARD)} runner reward</Text>
              </View>
              <Pressable
                onPress={checkout}
                disabled={post.isPending || posting}
                style={[s.cartBtn, (post.isPending || posting) && { opacity: 0.6 }]}
              >
                <Text style={s.cartBtnText}>
                  {post.isPending || posting ? "Posting…" : "Post errand →"}
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
  stale: {
    marginTop: space.lg,
    backgroundColor: colors.amberBg,
    borderColor: "#FDE68A",
  },

  add: {
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.brand,
    backgroundColor: colors.white,
  },
  addText: { color: colors.brand, fontSize: font.small, fontFamily: font.black, letterSpacing: 0.5 },

  step: {
    width: 30,
    height: 30,
    borderRadius: radius.md,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  stepGlyph: { color: colors.brandDark, fontSize: 16, fontFamily: font.bold },
  qty: {
    color: colors.ink,
    fontSize: font.body,
    fontFamily: font.bold,
    minWidth: 18,
    textAlign: "center",
  },

  cartBar: {
    position: "absolute",
    left: space.lg,
    right: space.lg,
    bottom: space.xl,
    borderRadius: radius.xl,
    padding: space.lg,
    backgroundColor: colors.brand,
  },
  cartCount: { color: colors.white, fontSize: font.h3, fontFamily: font.black },
  cartHint: { color: "rgba(255,255,255,0.85)", fontSize: font.tiny, fontFamily: font.medium, marginTop: 1 },
  cartBtn: {
    paddingHorizontal: space.lg,
    height: 42,
    borderRadius: radius.lg,
    backgroundColor: colors.white,
    alignItems: "center",
    justifyContent: "center",
  },
  cartBtnText: { color: colors.brand, fontSize: font.body, fontFamily: font.bold },
});
