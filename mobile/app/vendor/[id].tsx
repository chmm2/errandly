import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Location from "expo-location";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { createErrand } from "../../src/api/errands";
import { fetchMenu, type MenuItem } from "../../src/api/vendors";
import { Icon } from "../../src/components/icons";
import {
  Body,
  Button,
  Caption,
  EmptyState,
  Heading,
  Hero,
  Notice,
  Pill,
  Row,
  Screen,
  SkeletonRow,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { notify } from "../../src/lib/dialog";
import { goBack } from "../../src/lib/nav";
import { colors, font, radius, rupees, shadow, space } from "../../src/theme";

const DEFAULT_REWARD = 20;

export default function VendorMenu() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [cart, setCart] = useState<Record<string, number>>({});
  const [posting, setPosting] = useState(false);

  const { data, isLoading, isError, error, refetch } = useQuery({
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
    onError: (err) => notify("Couldn't post order", apiErrorMessage(err)),
  });

  async function checkout() {
    if (!data || lines.length === 0) return;
    setPosting(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") {
        notify("Location needed", "We need your location so the runner knows where to bring it.");
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

  // Same reasoning as the errand screen: an error must not masquerade as a
  // permanent loading state.
  if (isError || (!isLoading && !data)) {
    return (
      <Screen padded={false} edges={[]} tabBarClearance={false}>
        <Hero compact onBack={() => goBack(router)} title="Menu" />
        <View style={{ padding: 22 }}>
          <EmptyState
            icon="alert"
            title="Couldn't load this menu"
            body={error ? apiErrorMessage(error) : "It may have been removed, or the link is wrong."}
            action={<Button title="Try again" onPress={() => refetch()} />}
          />
        </View>
      </Screen>
    );
  }

  if (isLoading || !data) {
    return (
      <Screen padded={false} edges={[]} tabBarClearance={false}>
        <Hero compact onBack={() => goBack(router)} title="Loading menu…" />
        <View style={{ padding: 22, gap: space.sm }}>
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </View>
      </Screen>
    );
  }

  return (
    <Screen padded={false} edges={[]} bg={colors.bgSoft}>
      <View style={{ flex: 1 }}>
        <Screen scroll padded={false} edges={[]} bg={colors.bgSoft}>
          <Hero compact onBack={() => goBack(router)} title={data.vendor.name} subtitle={data.vendor.description ?? undefined}>
            <View style={{ marginTop: space.md, alignSelf: "flex-start" }}>
              <Pill
                label={data.vendor.is_open ? "Open now" : "Closed"}
                icon={data.vendor.is_open ? "clock" : "close"}
                bg="rgba(255,255,255,0.16)"
                color={colors.white}
              />
            </View>
          </Hero>

          <View style={{ paddingHorizontal: 22, paddingTop: space.lg, paddingBottom: 110 }}>
            {data.stale ? (
              <Notice
                icon="alert"
                title="Showing a slightly older menu"
                body="Live prices couldn't be reached, so these may have moved."
              />
            ) : null}

            {!data.vendor.is_open ? (
              <View style={[s.list, { padding: 14, marginTop: space.md }]}>
                <Caption>This store is closed right now, so orders can't be placed.</Caption>
              </View>
            ) : null}

            {sections.map(([section, items]) => (
              <View key={section} style={{ marginTop: space.xl }}>
                <Heading style={{ marginBottom: 10, fontSize: 16 }}>{section}</Heading>
                <View style={s.list}>
                  {items.map((item, i) => {
                    const qty = cart[item.id] ?? 0;
                    return (
                      <View key={item.id} style={i > 0 ? s.divider : undefined}>
                        <Row justify="space-between" gap={space.md} style={{ padding: 14 }}>
                          <View style={{ flex: 1 }}>
                            <Body
                              style={{
                                fontFamily: font.semi,
                                color: item.is_available ? colors.ink : colors.muted,
                              }}
                            >
                              {item.name}
                            </Body>
                            <Caption style={{ marginTop: 2, color: colors.moneyText, fontFamily: font.bold }}>
                              {rupees(item.price)}
                            </Caption>
                            {!item.is_available ? (
                              <Caption style={{ color: colors.caution }}>Sold out</Caption>
                            ) : null}
                          </View>

                          {item.is_available && data.vendor.is_open ? (
                            qty > 0 ? (
                              <View style={s.stepper}>
                                <Pressable
                                  onPress={() => bump(item.id, -1)}
                                  style={s.stepBtn}
                                  hitSlop={6}
                                  accessibilityRole="button"
                                  accessibilityLabel="One fewer"
                                >
                                  <Icon name="minus" size={15} color={colors.brand} />
                                </Pressable>
                                <Text style={s.qty}>{qty}</Text>
                                <Pressable
                                  onPress={() => bump(item.id, 1)}
                                  style={s.stepBtn}
                                  hitSlop={6}
                                  accessibilityRole="button"
                                  accessibilityLabel="One more"
                                >
                                  <Icon name="plus" size={15} color={colors.brand} />
                                </Pressable>
                              </View>
                            ) : (
                              <Pressable
                                onPress={() => bump(item.id, 1)}
                                style={s.add}
                                accessibilityRole="button"
                                accessibilityLabel={"Add " + item.name}
                              >
                                <Icon name="plus" size={16} color={colors.white} />
                              </Pressable>
                            )
                          ) : null}
                        </Row>
                      </View>
                    );
                  })}
                </View>
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
                  {count} item{count > 1 ? "s" : ""}, {rupees(total)}
                </Text>
                <Text style={s.cartHint}>plus {rupees(DEFAULT_REWARD)} runner reward</Text>
              </View>
              <Pressable
                onPress={checkout}
                disabled={post.isPending || posting}
                style={[s.cartBtn, (post.isPending || posting) && { opacity: 0.6 }]}
              >
                <Text style={s.cartBtnText}>
                  {post.isPending || posting ? "Posting…" : "Post errand"}
                </Text>
                {post.isPending || posting ? null : (
                  <Icon name="chev" size={17} color={colors.brand} />
                )}
              </Pressable>
            </Row>
          </View>
        ) : null}
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  list: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.xxl,
    overflow: "hidden",
  },
  divider: { borderTopWidth: 1, borderTopColor: colors.hairlineSoft },

  add: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
  stepper: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.sm,
    height: 34,
  },
  stepBtn: { paddingHorizontal: 8, height: "100%", justifyContent: "center" },
  qty: {
    color: colors.ink,
    fontSize: 13,
    fontFamily: font.bold,
    minWidth: 14,
    textAlign: "center",
  },

  cartBar: {
    position: "absolute",
    left: 22,
    right: 22,
    bottom: space.xl,
    borderRadius: radius.xl,
    padding: space.lg,
    backgroundColor: colors.brand,
  },
  cartCount: { color: colors.white, fontSize: 16, fontFamily: font.black },
  cartHint: { color: "rgba(255,255,255,0.78)", fontSize: 11, fontFamily: font.regular, marginTop: 1 },
  cartBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: space.lg,
    height: 42,
    borderRadius: radius.md,
    backgroundColor: colors.white,
    justifyContent: "center",
  },
  cartBtnText: { color: colors.brand, fontSize: 14, fontFamily: font.bold },
});
