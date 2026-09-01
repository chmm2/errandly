import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as Location from "expo-location";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { type Category, createErrand } from "../../src/api/errands";
import {
  Body,
  Button,
  Caption,
  Card,
  ErrorNote,
  Field,
  Label,
  Row,
  Screen,
  Title,
} from "../../src/components/ui";
import type { ReferenceSuggestion } from "../../src/api/fraud";
import { ItemSearchField } from "../../src/components/ItemSearchField";
import { apiErrorMessage } from "../../src/lib/api";
import { goBack } from "../../src/lib/nav";
import { categoryIcon, colors, font, radius, space } from "../../src/theme";

/**
 * The only flow that asks for a category is the shopping list — "groceries,
 * stationery, medicines" is one journey with three shelves. Every other entry
 * point already told us what it is by being tapped, so re-asking is a step for
 * nothing.
 */
const SHOPPING_CATEGORIES: { value: Category; label: string }[] = [
  { value: "GROCERY", label: "Grocery" },
  { value: "STATIONERY", label: "Stationery" },
  { value: "PHARMACY", label: "Pharmacy" },
];

/** Screen title and lead-in per entry point. */
const FLOW_COPY: Record<string, { title: string; blurb: string }> = {
  shopping: {
    title: "Shopping list",
    blurb: "List what you need and a runner picks it up off the shelf.",
  },
  PARCEL: {
    title: "Parcel pickup",
    blurb: "Someone collects your parcel from the campus collection point.",
  },
  CUSTOM: {
    title: "Main gate",
    blurb: "Someone collects a delivery waiting for you at the gate.",
  },
  FOOD: { title: "New errand", blurb: "Tell a runner what you need and what it's worth." },
};

/** Backend derives fulfillment from category; these two need handoff details. */
const PICKUP_CATEGORIES: Category[] = ["CUSTOM", "PARCEL"];
const WAIT_OPTIONS = [15, 30, 45, 60];
const REWARD_PRESETS = [10, 20, 30, 50];

/**
 * Who the delivery is from.
 *
 * A pickup errand does not need "what do you need?" — the parcel is already
 * bought and already there. What the runner has to be told is which counter to
 * stand at, and that is the courier. The two flows get different lists because
 * a parcel at the collection point and a bag at the gate come from different
 * companies.
 */
const COURIERS: Record<string, string[]> = {
  PARCEL: [
    "Amazon", "Flipkart", "Delhivery", "Blue Dart",
    "DTDC", "Ekart", "India Post", "Other",
  ],
  CUSTOM: [
    "Swiggy", "Zomato", "Zepto", "Blinkit",
    "Instamart", "Amazon", "Flipkart", "Other",
  ],
};

/** Where each pickup flow physically happens. Fixed, so it is not asked. */
const FIXED_PICKUP: Record<string, string> = {
  PARCEL: "Campus collection point",
  CUSTOM: "Main gate",
};

/** One line of a shopping list. */
interface ListRow {
  name: string;
  quantity: number;
  // Set when the line was picked off the admin's non-MRP price list. It
  // is what earns the line escrow headroom, so it travels with the order.
  ref?: ReferenceSuggestion | null;
}

export default function NewErrand() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const params = useLocalSearchParams<{ category?: Category; mode?: string }>();

  const isShopping = params.mode === "shopping";
  const [category, setCategory] = useState<Category>(
    params.category ?? (isShopping ? "GROCERY" : "FOOD"),
  );
  const copy = FLOW_COPY[isShopping ? "shopping" : (params.category ?? "FOOD")] ?? FLOW_COPY.FOOD;
  const [notes, setNotes] = useState("");
  // Shopping lists are structured, not prose. A typed sentence cannot be
  // priced, and price checking is what catches an inflated claim — the runner
  // reports a unit price per line, and a line needs a name and a quantity to
  // report against.
  const [rows, setRows] = useState<ListRow[]>([{ name: "", quantity: 1, ref: null }]);
  const [courier, setCourier] = useState("");
  const [courierOther, setCourierOther] = useState("");
  const [reward, setReward] = useState("20");
  const [waitMinutes, setWaitMinutes] = useState(30);
  const [externalRef, setExternalRef] = useState("");
  const [otp, setOtp] = useState("");
  const [collect, setCollect] = useState("");
  const [drop, setDrop] = useState<{ lat: number; lng: number } | null>(null);
  const [locating, setLocating] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isPickup = PICKUP_CATEGORIES.includes(category);

  // Drop point defaults to where you're standing — you almost always want the
  // delivery to come to you.
  useEffect(() => {
    (async () => {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status !== "granted") return;
        const pos = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });
        setDrop({ lat: pos.coords.latitude, lng: pos.coords.longitude });
      } catch {
        // leave drop null; the guard below explains it
      } finally {
        setLocating(false);
      }
    })();
  }, []);

  const create = useMutation({
    mutationFn: createErrand,
    onSuccess: (errand) => {
      queryClient.invalidateQueries({ queryKey: ["my-errands"] });
      router.replace(`/errand/${errand.id}`);
    },
    onError: (err) => setError(apiErrorMessage(err, "Couldn't post that errand.")),
  });

  const rewardNum = Number(reward) || 0;

  const filledRows = rows.filter((r) => r.name.trim().length > 0);
  const chosenCourier = courier === "Other" ? courierOther.trim() : courier;

  // Both title and pickup_label are required server-side. Where the flow no
  // longer asks for them they are derived, so the errand still reads properly
  // in a feed and an admin log without the requester typing what the app
  // already knows.
  const derivedTitle = isShopping
    ? filledRows.length === 1
      ? `${filledRows[0].quantity} × ${filledRows[0].name.trim()}`
      : `${filledRows.length} items`
    : chosenCourier
      ? `${chosenCourier} pickup`
      : "";
  const derivedPickup = isShopping
    ? // The runner decides which shop is nearest to them; naming one would be
      // guessing on their behalf.
      "Runner's choice"
    : FIXED_PICKUP[category] ?? "Main gate";

  const ready = isShopping
    ? filledRows.length > 0 && !!drop
    : chosenCourier.length >= 2 && !!drop;

  function setRow(i: number, patch: Partial<ListRow>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function submit() {
    if (!drop) return;
    setError(null);
    create.mutate({
      category,
      title: derivedTitle.slice(0, 200),
      notes: notes.trim() || undefined,
      pickup_label: derivedPickup,
      ...(isShopping && filledRows.length
        ? {
            list_items: filledRows.map((r) => ({
              name: r.name.trim(),
              quantity: r.quantity,
              // Only the id travels. The server re-reads the price from that
              // row, so nothing sent from here can change what gets held.
              reference_id: r.ref?.reference_id,
            })),
          }
        : {}),
      drop_lat: drop.lat,
      drop_lng: drop.lng,
      reward: rewardNum,
      wait_minutes: waitMinutes,
      ...(isPickup
        ? {
            external_ref: externalRef.trim() || undefined,
            otp: otp.trim() || undefined,
            collect_amount: Number(collect) || 0,
          }
        : {}),
    });
  }

  return (
    <Screen padded={false}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxxl }}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <Row justify="flex-end">
            <Pressable onPress={() => goBack(router)} style={s.close} hitSlop={12}>
              <Text style={s.closeGlyph}>✕</Text>
            </Pressable>
          </Row>

          <Row gap={space.sm} align="center" style={{ marginTop: space.sm }}>
            <Text style={{ fontSize: 26 }}>{categoryIcon[category] ?? "✨"}</Text>
            <Title>{copy.title}</Title>
          </Row>
          <Body muted style={{ marginTop: space.xs }}>
            {copy.blurb}
          </Body>

          {/* Only the shopping-list flow needs a choice — every other entry
              point already picked the category by being tapped. */}
          {isShopping ? (
            <>
              <Label style={{ marginTop: space.xxl, marginBottom: space.md }}>What kind?</Label>
              <Row gap={space.sm}>
                {SHOPPING_CATEGORIES.map((c) => {
                  const on = c.value === category;
                  return (
                    <Pressable
                      key={c.value}
                      onPress={() => setCategory(c.value)}
                      style={[s.cat, on && s.catOn]}
                    >
                      <Text style={{ fontSize: 18 }}>{categoryIcon[c.value]}</Text>
                      <Caption
                        style={{
                          color: on ? colors.brandDark : colors.muted,
                          fontFamily: font.semi,
                          marginTop: 2,
                        }}
                      >
                        {c.label}
                      </Caption>
                    </Pressable>
                  );
                })}
              </Row>
            </>
          ) : null}

          <View style={{ gap: space.lg, marginTop: space.xxl }}>
            {isShopping ? (
              /* A list, not a sentence. Each line carries its own quantity,
                 because the runner reports a unit price against it later and
                 a price check needs to know how many were bought. */
              <View style={{ gap: 6 }}>
                <Label>Your list</Label>
                <View style={{ gap: space.sm }}>
                  {rows.map((row, i) => (
                    <Row key={i} gap={space.sm}>
                      <View style={{ flex: 1 }}>
                        <ItemSearchField
                          placeholder={
                            i === 0
                              ? "Search the campus price list"
                              : "Add another item"
                          }
                          value={row.name}
                          picked={row.ref ?? null}
                          onChangeText={(v) => setRow(i, { name: v })}
                          onPick={(ref) => setRow(i, { ref })}
                        />
                      </View>

                      {/* A stepper rather than a keypad: quantities here are
                          small, and tapping beats typing for 1 to 5. */}
                      <Row gap={0} style={s.qty}>
                        <Pressable
                          onPress={() => setRow(i, { quantity: Math.max(1, row.quantity - 1) })}
                          style={s.qtyBtn}
                          hitSlop={6}
                        >
                          <Text style={s.qtyGlyph}>−</Text>
                        </Pressable>
                        <Text style={s.qtyValue}>{row.quantity}</Text>
                        <Pressable
                          onPress={() => setRow(i, { quantity: Math.min(50, row.quantity + 1) })}
                          style={s.qtyBtn}
                          hitSlop={6}
                        >
                          <Text style={s.qtyGlyph}>+</Text>
                        </Pressable>
                      </Row>

                      <Pressable
                        onPress={() =>
                          setRows((prev) =>
                            prev.length === 1
                              ? [{ name: "", quantity: 1, ref: null }]
                              : prev.filter((_, idx) => idx !== i),
                          )
                        }
                        style={s.rowRemove}
                        hitSlop={8}
                      >
                        <Text style={s.rowRemoveGlyph}>×</Text>
                      </Pressable>
                    </Row>
                  ))}
                </View>

                <Pressable
                  onPress={() => setRows((prev) => [...prev, { name: "", quantity: 1, ref: null }])}
                  style={s.addRow}
                >
                  <Text style={s.addRowText}>+  Add item</Text>
                </Pressable>

                <Caption>
                  A runner picks these up from whichever shop is closest to them.
                </Caption>
              </View>
            ) : (
              /* Pickups do not need "what do you need" — the parcel exists and
                 is already paid for. What the runner needs is the counter. */
              <View style={{ gap: 6 }}>
                <Label>Who is it from?</Label>
                <Row gap={space.sm} wrap>
                  {(COURIERS[category] ?? COURIERS.CUSTOM).map((c) => {
                    const on = courier === c;
                    return (
                      <Pressable
                        key={c}
                        onPress={() => setCourier(c)}
                        style={[s.courier, on && s.courierOn]}
                      >
                        <Caption
                          style={{
                            color: on ? colors.brandDark : colors.ink,
                            fontFamily: font.semi,
                          }}
                        >
                          {c}
                        </Caption>
                      </Pressable>
                    );
                  })}
                </Row>

                {courier === "Other" ? (
                  <View style={{ marginTop: space.sm }}>
                    <Field
                      placeholder="Who delivered it?"
                      value={courierOther}
                      onChangeText={setCourierOther}
                      maxLength={60}
                    />
                  </View>
                ) : null}

                <Caption style={{ marginTop: space.xs }}>
                  Collected from the {(FIXED_PICKUP[category] ?? "main gate").toLowerCase()}.
                </Caption>
              </View>
            )}

            <Field
              label="Notes (optional)"
              placeholder="No onions, extra napkins…"
              value={notes}
              onChangeText={setNotes}
              multiline
              style={{ minHeight: 84, textAlignVertical: "top" }}
              maxLength={2000}
            />

            {/* Reward */}
            <View style={{ gap: 6 }}>
              <Label>Reward for the runner</Label>
              <Row gap={space.sm}>
                <Field
                  value={reward}
                  onChangeText={setReward}
                  keyboardType="number-pad"
                  // Fixed width, not flex: at flex:1 the input took the whole
                  // row and pushed the last preset off the screen edge. Four
                  // digits is more reward than anyone will offer.
                  style={s.rewardInput}
                  placeholder="20"
                />
                {REWARD_PRESETS.map((v) => (
                  <Pressable
                    key={v}
                    onPress={() => setReward(String(v))}
                    style={[s.preset, rewardNum === v && s.presetOn]}
                  >
                    <Caption
                      style={{
                        color: rewardNum === v ? colors.brandDark : colors.ink,
                        fontFamily: font.bold,
                      }}
                    >
                      ₹{v}
                    </Caption>
                  </Pressable>
                ))}
              </Row>
            </View>

            {/* Wait window */}
            <View style={{ gap: 6 }}>
              <Label>Wait up to</Label>
              <Row gap={space.sm}>
                {WAIT_OPTIONS.map((m) => {
                  const on = m === waitMinutes;
                  return (
                    <Pressable
                      key={m}
                      onPress={() => setWaitMinutes(m)}
                      style={[s.wait, on && s.waitOn]}
                    >
                      <Caption
                        style={{
                          color: on ? colors.brandDark : colors.muted,
                          fontFamily: font.bold,
                        }}
                      >
                        {m}m
                      </Caption>
                    </Pressable>
                  );
                })}
              </Row>
              <Caption>Expires automatically if nobody accepts in time.</Caption>
            </View>

            {/* Gate / parcel handoff */}
            {isPickup ? (
              <Card style={{ gap: space.lg, backgroundColor: colors.brandSoft }}>
                <View>
                  <Body style={{ fontFamily: font.bold }}>🔐 Handoff details</Body>
                  <Caption style={{ marginTop: 2 }}>
                    Shared only with the runner who accepts, and every view is logged.
                  </Caption>
                </View>
                <Field
                  label="Order / tracking number"
                  placeholder="e.g. 4821-9930"
                  value={externalRef}
                  onChangeText={setExternalRef}
                  autoCapitalize="characters"
                />
                <Field
                  label="Delivery OTP (optional)"
                  placeholder="If the courier needs one"
                  value={otp}
                  onChangeText={setOtp}
                  keyboardType="number-pad"
                />
                <Field
                  label="Cash the runner pays (optional)"
                  placeholder="0"
                  value={collect}
                  onChangeText={setCollect}
                  keyboardType="number-pad"
                  hint="Reimbursed on top of the reward when you confirm."
                />
              </Card>
            ) : null}

            {/* Drop location */}
            <Card style={{ backgroundColor: colors.brandSoft }}>
              <Row gap={space.sm} align="flex-start">
                <Text style={{ fontSize: 15 }}>📍</Text>
                <View style={{ flex: 1 }}>
                  <Body style={{ fontFamily: font.bold }}>Deliver to my location</Body>
                  <Caption style={{ marginTop: 2 }}>
                    {locating
                      ? "Finding you…"
                      : drop
                        ? `${drop.lat.toFixed(5)}, ${drop.lng.toFixed(5)}`
                        : "Location unavailable — enable location access to post."}
                  </Caption>
                </View>
              </Row>
            </Card>

            {error ? <ErrorNote>{error}</ErrorNote> : null}

            <Button
              title="Post errand"
              size="lg"
              loading={create.isPending}
              disabled={!ready}
              onPress={submit}
            />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const s = StyleSheet.create({
  rewardInput: { width: 74, textAlign: "center" },

  qty: {
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.lg,
    backgroundColor: colors.white,
    alignItems: "center",
  },
  qtyBtn: { paddingHorizontal: 10, paddingVertical: 9 },
  qtyGlyph: { color: colors.brandDark, fontSize: 17, fontFamily: font.bold },
  qtyValue: {
    minWidth: 20,
    textAlign: "center",
    color: colors.ink,
    fontSize: font.body,
    fontFamily: font.bold,
  },
  rowRemove: { paddingHorizontal: 4, paddingVertical: 8 },
  rowRemoveGlyph: { color: colors.muted, fontSize: 19, fontFamily: font.bold },

  addRow: {
    alignSelf: "flex-start",
    paddingHorizontal: space.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: colors.brandSoft,
    marginTop: 2,
  },
  addRowText: { color: colors.brandDark, fontSize: font.small, fontFamily: font.bold },

  courier: {
    paddingHorizontal: space.md,
    paddingVertical: 9,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
  },
  courierOn: { borderColor: colors.brand, backgroundColor: colors.brandSoft },

  close: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  closeGlyph: { color: colors.brandDark, fontSize: 15, fontFamily: font.bold },

  cat: {
    width: "31.5%",
    paddingVertical: space.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
    alignItems: "center",
  },
  catOn: { borderColor: colors.brand, backgroundColor: colors.brandSoft },

  preset: {
    paddingHorizontal: space.md,
    height: 48,
    borderRadius: radius.lg,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
    alignItems: "center",
    justifyContent: "center",
  },
  presetOn: { borderColor: colors.brand, backgroundColor: colors.brandSoft },

  wait: {
    flex: 1,
    paddingVertical: space.md,
    borderRadius: radius.lg,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
    alignItems: "center",
  },
  waitOn: { borderColor: colors.brand, backgroundColor: colors.brandSoft },
});
