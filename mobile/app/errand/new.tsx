import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Svg, { Circle, Path, Rect } from "react-native-svg";

import { type Category, createErrand } from "../../src/api/errands";
import type { ReferenceSuggestion } from "../../src/api/fraud";
import { fetchWallet } from "../../src/api/wallet";
import { Icon, type IconName } from "../../src/components/icons";
import { ItemSearchField } from "../../src/components/ItemSearchField";
import { Button, ErrorNote, Field, StepDots } from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { goBack } from "../../src/lib/nav";
import { categoryIcon, colors, font, radius, space } from "../../src/theme";

/**
 * The only flow that asks for a category is the shopping list: "groceries,
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
  shopping: { title: "Shopping list", blurb: "Runner picks it off the nearest shelf" },
  PARCEL: { title: "Parcel pickup", blurb: "Collected from the campus collection point" },
  CUSTOM: { title: "Main gate", blurb: "Collected from the main gate" },
  FOOD: { title: "New errand", blurb: "Tell a runner what you need" },
};

/** Backend derives fulfillment from category; these two need handoff details. */
const PICKUP_CATEGORIES: Category[] = ["CUSTOM", "PARCEL"];
const WAIT_OPTIONS = [15, 30, 45, 60];
const REWARD_PRESETS = [10, 20, 30, 50];

/**
 * How long an errand stays with friends and friends of friends before the
 * offer widens. Mirrors the first entry of SOCIAL_TIERS in
 * backend/app/workers/consumers.py, which is what actually times it; change
 * the two together.
 */
const FRIENDS_FIRST_SECONDS = 45;

/**
 * Who the delivery is from.
 *
 * A pickup errand does not need "what do you need?": the parcel is already
 * bought and already there. What the runner has to be told is which counter to
 * stand at, and that is the courier. The two flows get different lists because
 * a parcel at the collection point and a bag at the gate come from different
 * companies.
 */
const COURIERS: Record<string, string[]> = {
  PARCEL: ["Amazon", "Flipkart", "Delhivery", "Blue Dart", "DTDC", "Ekart", "India Post", "Other"],
  CUSTOM: ["Swiggy", "Zomato", "Zepto", "Blinkit", "Instamart", "Amazon", "Flipkart", "Other"],
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
  // Set when the line was picked off the admin's non-MRP price list. It is
  // what earns the line escrow headroom, so it travels with the order.
  ref: ReferenceSuggestion | null;
}

/** Money with paise only when there are any, so ₹86 never reads as ₹86.00. */
function money(n: number): string {
  const r = Math.round(n * 100) / 100;
  return Number.isInteger(r) ? `₹${r}` : `₹${r.toFixed(2)}`;
}

export default function NewErrand() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const params = useLocalSearchParams<{ category?: Category; mode?: string }>();

  const isShopping = params.mode === "shopping";
  const [step, setStep] = useState<1 | 2>(1);
  const [category, setCategory] = useState<Category>(
    params.category ?? (isShopping ? "GROCERY" : "FOOD"),
  );
  const copy = FLOW_COPY[isShopping ? "shopping" : (params.category ?? "FOOD")] ?? FLOW_COPY.FOOD;
  const [notes, setNotes] = useState("");
  // Shopping lists are structured, not prose. A typed sentence cannot be
  // priced, and price checking is what catches an inflated claim: the runner
  // reports a unit price per line, and a line needs a name and a quantity to
  // report against.
  const [rows, setRows] = useState<ListRow[]>([]);
  const [courier, setCourier] = useState("");
  const [courierOther, setCourierOther] = useState("");
  const [reward, setReward] = useState(20);
  const [customReward, setCustomReward] = useState(false);
  const [waitMinutes, setWaitMinutes] = useState(30);
  const [externalRef, setExternalRef] = useState("");
  const [otp, setOtp] = useState("");
  const [collect, setCollect] = useState("");
  const [dropLabel, setDropLabel] = useState("");
  const [drop, setDrop] = useState<{ lat: number; lng: number } | null>(null);
  const [locating, setLocating] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isPickup = PICKUP_CATEGORIES.includes(category);

  // The headroom rate comes from the server, so the bill below quotes the same
  // hold the ledger will place.
  const { data: wallet } = useQuery({ queryKey: ["wallet"], queryFn: fetchWallet });

  // Drop point defaults to where you're standing: you almost always want the
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
        // leave drop null; the delivery card explains it
      } finally {
        setLocating(false);
      }
    })();
  }, []);

  const create = useMutation({
    mutationFn: createErrand,
    onSuccess: (errand) => {
      queryClient.invalidateQueries({ queryKey: ["my-errands"] });
      queryClient.invalidateQueries({ queryKey: ["wallet"] });
      router.replace(`/errand/${errand.id}`);
    },
    onError: (err) => setError(apiErrorMessage(err, "Couldn't post that errand.")),
  });

  const chosenCourier = courier === "Other" ? courierOther.trim() : courier;
  const collectNum = isPickup ? Number(collect) || 0 : 0;

  /*
   * The bill, computed the way the ledger computes the hold:
   *
   *   hold = priced items + cash at pickup + priced items x buffer_pct + reward
   *
   * Only lines picked off the price list carry a price, and only those earn
   * headroom. Hand-typed lines are reported by the runner afterwards and are
   * not part of what is held.
   */
  const pricedTotal = rows.reduce(
    (sum, r) => sum + (r.ref ? r.ref.reference_price * r.quantity : 0),
    0,
  );
  const bufferPct = wallet?.buffer_pct;
  const buffer = bufferPct != null ? Math.round(pricedTotal * bufferPct * 100) / 100 : null;
  const hold = buffer != null ? pricedTotal + collectNum + buffer + reward : null;
  const unpriced = rows.filter((r) => !r.ref).length;

  // Both title and pickup_label are required server side. Where the flow no
  // longer asks for them they are derived, so the errand still reads properly
  // in a feed and an admin log without the requester typing what the app
  // already knows.
  const derivedTitle = isShopping
    ? rows.length === 1
      ? `${rows[0].quantity} × ${rows[0].name.trim()}`
      : `${rows.length} items`
    : chosenCourier
      ? `${chosenCourier} pickup`
      : "";
  const derivedPickup = isShopping
    ? // The runner decides which shop is nearest to them; naming one would be
      // guessing on their behalf.
      "Runner's choice"
    : (FIXED_PICKUP[category] ?? "Main gate");

  const stepOneReady = isShopping ? rows.length > 0 : chosenCourier.length >= 2;
  const ready = stepOneReady && !!drop && reward > 0;

  function addLine(name: string, ref: ReferenceSuggestion | null) {
    setRows((prev) => {
      // Picking the same priced item twice bumps its quantity rather than
      // listing it twice, which is what the person meant.
      const same = prev.findIndex((r) =>
        ref ? r.ref?.reference_id === ref.reference_id : !r.ref && r.name === name,
      );
      if (same >= 0) {
        return prev.map((r, i) => (i === same ? { ...r, quantity: Math.min(50, r.quantity + 1) } : r));
      }
      return [...prev, { name, quantity: 1, ref }];
    });
  }

  function setQty(i: number, q: number) {
    setRows((prev) =>
      q <= 0 ? prev.filter((_, idx) => idx !== i) : prev.map((r, idx) => (idx === i ? { ...r, quantity: Math.min(50, q) } : r)),
    );
  }

  function submit() {
    if (!drop) return;
    setError(null);
    create.mutate({
      category,
      title: derivedTitle.slice(0, 200),
      notes: notes.trim() || undefined,
      pickup_label: derivedPickup,
      ...(isShopping && rows.length
        ? {
            list_items: rows.map((r) => ({
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
      drop_label: dropLabel.trim() || undefined,
      reward,
      wait_minutes: waitMinutes,
      ...(isPickup
        ? {
            external_ref: externalRef.trim() || undefined,
            otp: otp.trim() || undefined,
            collect_amount: collectNum,
          }
        : {}),
    });
  }

  const stepOneSummary = isShopping
    ? `${SHOPPING_CATEGORIES.find((c) => c.value === category)?.label ?? "Shopping"}, ${rows.length} line${rows.length === 1 ? "" : "s"}`
    : `${chosenCourier || "Pickup"}, ${(FIXED_PICKUP[category] ?? "main gate").toLowerCase()}`;
  const stepOneDetail = isShopping
    ? rows.map((r) => r.name).join(", ")
    : externalRef.trim()
      ? `Order ref ${externalRef.trim()}`
      : "No order reference given";

  return (
    <SafeAreaView style={s.root} edges={["top", "bottom"]}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        {/* Header */}
        <View style={s.header}>
          <Pressable
            onPress={() => (step === 2 ? setStep(1) : goBack(router))}
            style={({ pressed }) => [
              s.headBtn,
              { backgroundColor: step === 2 ? colors.brandTint : colors.chip },
              pressed && { opacity: 0.7 },
            ]}
            hitSlop={12}
            accessibilityRole="button"
            accessibilityLabel={step === 2 ? "Back to your list" : "Close"}
          >
            <Icon
              name={step === 2 ? "back" : "close"}
              size={18}
              color={step === 2 ? colors.brand : colors.inkSoft}
            />
          </Pressable>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={s.headTitle}>{step === 1 ? copy.title : "Reward and delivery"}</Text>
            <Text style={s.headSub}>
              {step === 1 ? copy.blurb : "Last step before it goes out"}
            </Text>
          </View>
          <StepDots total={3} done={step === 1 ? 2 : 3} />
        </View>

        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={s.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {step === 1 ? (
            <>
              {isShopping ? (
                <>
                  {/* 1. shelf */}
                  <Section n={1} title="Which shelf">
                    <View style={s.segment}>
                      {SHOPPING_CATEGORIES.map((c) => {
                        const on = c.value === category;
                        return (
                          <Pressable
                            key={c.value}
                            onPress={() => setCategory(c.value)}
                            style={[s.segItem, on && s.segItemOn]}
                            accessibilityRole="tab"
                            accessibilityState={{ selected: on }}
                          >
                            <Icon
                              name={categoryIcon[c.value as keyof typeof categoryIcon] as IconName}
                              size={16}
                              color={on ? colors.brand : colors.mutedCool}
                            />
                            <Text style={[s.segText, on && { color: colors.brand }]}>
                              {c.label}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  </Section>

                  {/* 2. list */}
                  <Section
                    n={2}
                    title="What to buy"
                    right={
                      rows.length
                        ? `${rows.length} line${rows.length === 1 ? "" : "s"}${pricedTotal > 0 ? `, ${money(pricedTotal)}` : ""}`
                        : undefined
                    }
                  >
                    <ItemSearchField onAdd={addLine} />

                    {rows.length > 0 ? (
                      <View style={s.lines}>
                        {rows.map((r, i) => (
                          <View key={`${r.name}-${i}`} style={[s.line, i > 0 && s.lineDivider]}>
                            <View style={s.lineIcon}>
                              <Icon name={r.ref ? "cash" : "bag"} size={18} color={colors.brand} />
                            </View>
                            <View style={{ flex: 1, minWidth: 0 }}>
                              <Text numberOfLines={1} style={s.lineName}>
                                {r.name}
                              </Text>
                              {r.ref ? (
                                <View style={s.listedRow}>
                                  <Icon name="check" size={12} color={colors.credit} />
                                  <Text style={s.listed}>
                                    Listed at {money(r.ref.reference_price)} each
                                  </Text>
                                </View>
                              ) : (
                                <Text style={s.unlisted}>
                                  Not on the price list, runner reports it
                                </Text>
                              )}
                            </View>

                            {/* A stepper rather than a keypad: quantities here
                                are small, and tapping beats typing for 1 to 5.
                                Stepping below one removes the line. */}
                            <View style={s.stepper}>
                              <Pressable
                                onPress={() => setQty(i, r.quantity - 1)}
                                style={s.stepBtn}
                                hitSlop={6}
                                accessibilityRole="button"
                                accessibilityLabel={r.quantity === 1 ? `Remove ${r.name}` : "One fewer"}
                              >
                                <Icon
                                  name={r.quantity === 1 ? "close" : "minus"}
                                  size={15}
                                  color={colors.brand}
                                />
                              </Pressable>
                              <Text style={s.stepValue}>{r.quantity}</Text>
                              <Pressable
                                onPress={() => setQty(i, r.quantity + 1)}
                                style={s.stepBtn}
                                hitSlop={6}
                                accessibilityRole="button"
                                accessibilityLabel="One more"
                              >
                                <Icon name="plus" size={15} color={colors.brand} />
                              </Pressable>
                            </View>
                            <Text style={[s.lineTotal, !r.ref && { color: colors.mutedCool }]}>
                              {r.ref ? Math.round(r.ref.reference_price * r.quantity) : "—"}
                            </Text>
                          </View>
                        ))}
                      </View>
                    ) : (
                      <Text style={s.hint}>
                        Search for an item and tap it to add it. A runner buys from whichever
                        shop is closest to them.
                      </Text>
                    )}
                  </Section>
                </>
              ) : (
                <>
                  {/* Pickups do not need "what do you need": the parcel exists
                      and is already paid for. What the runner needs is the
                      counter. */}
                  <Section n={1} title="Who is it from">
                    <View style={s.chips}>
                      {(COURIERS[category] ?? COURIERS.CUSTOM).map((c) => {
                        const on = courier === c;
                        return (
                          <Pressable
                            key={c}
                            onPress={() => setCourier(c)}
                            style={[s.chip, on && s.chipOn]}
                          >
                            <Text style={[s.chipText, on && { color: colors.white }]}>{c}</Text>
                          </Pressable>
                        );
                      })}
                    </View>
                    {courier === "Other" ? (
                      <Field
                        placeholder="Who delivered it?"
                        value={courierOther}
                        onChangeText={setCourierOther}
                        maxLength={60}
                      />
                    ) : null}
                  </Section>

                  <Section n={2} title="Handoff details">
                    <View style={s.handoff}>
                      <View style={s.handoffHead}>
                        <Icon name="lock" size={17} color={colors.brand} />
                        <Text style={s.handoffNote}>
                          Shared only with the runner who accepts, and every view is logged.
                        </Text>
                      </View>
                      <Field
                        label="Order or tracking number"
                        placeholder="e.g. 4821-9930"
                        value={externalRef}
                        onChangeText={setExternalRef}
                        autoCapitalize="characters"
                        mono
                      />
                      <Field
                        label="Delivery OTP (optional)"
                        placeholder="If the courier needs one"
                        value={otp}
                        onChangeText={setOtp}
                        keyboardType="number-pad"
                        mono
                      />
                      <Field
                        label="Cash the runner pays (optional)"
                        placeholder="0"
                        value={collect}
                        onChangeText={setCollect}
                        keyboardType="number-pad"
                        hint="Reimbursed on top of the reward when you confirm."
                      />
                    </View>
                  </Section>
                </>
              )}

              <Field
                label="Notes (optional)"
                placeholder="No onions, extra napkins…"
                value={notes}
                onChangeText={setNotes}
                multiline
                style={{ minHeight: 72, textAlignVertical: "top" }}
                maxLength={2000}
              />
            </>
          ) : (
            <>
              {/* What step one decided, with a way back to change it. */}
              <View style={s.summary}>
                <View style={s.lineIcon}>
                  <Icon
                    name={(categoryIcon[category as keyof typeof categoryIcon] ?? "gate") as IconName}
                    size={19}
                    color={colors.brand}
                  />
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.summaryTitle}>{stepOneSummary}</Text>
                  <Text numberOfLines={1} style={s.summarySub}>
                    {stepOneDetail}
                  </Text>
                </View>
                <Pressable onPress={() => setStep(1)} hitSlop={8}>
                  <Text style={s.link}>Edit</Text>
                </Pressable>
              </View>

              {/* 3. terms */}
              <Section n={3} title="Reward and timing">
                <View style={s.card}>
                  <Text style={s.rewardLabel}>Reward for the runner</Text>
                  <View style={s.rewardRow}>
                    <Text style={s.rewardRupee}>₹</Text>
                    {customReward ? (
                      <TextInput
                        value={reward ? String(reward) : ""}
                        onChangeText={(v) => setReward(Math.min(9999, Number(v.replace(/\D/g, "")) || 0))}
                        keyboardType="number-pad"
                        autoFocus
                        style={s.rewardInput}
                        maxLength={4}
                        placeholder="0"
                        placeholderTextColor={colors.mutedCool}
                      />
                    ) : (
                      <Text style={s.rewardValue}>{reward}</Text>
                    )}
                  </View>

                  <View style={s.presets}>
                    {REWARD_PRESETS.map((v) => {
                      const on = !customReward && reward === v;
                      return (
                        <Pressable
                          key={v}
                          onPress={() => {
                            setCustomReward(false);
                            setReward(v);
                          }}
                          style={[s.preset, on && s.presetOn]}
                        >
                          <Text style={[s.presetText, on && s.presetTextOn]}>{v}</Text>
                        </Pressable>
                      );
                    })}
                    <Pressable
                      onPress={() => setCustomReward(true)}
                      style={[s.presetCustom, customReward && s.presetOn]}
                      accessibilityRole="button"
                      accessibilityLabel="Enter your own reward"
                    >
                      <Icon name="plus" size={16} color={customReward ? colors.brand : colors.mutedCool} />
                    </Pressable>
                  </View>

                  <View style={s.waitRow}>
                    <Icon name="clock" size={17} color={colors.mutedCool} />
                    <Text style={s.waitLabel}>Wait up to</Text>
                    <View style={s.waitPills}>
                      {WAIT_OPTIONS.map((m) => {
                        const on = m === waitMinutes;
                        return (
                          <Pressable
                            key={m}
                            onPress={() => setWaitMinutes(m)}
                            style={[s.waitPill, on && s.waitPillOn]}
                          >
                            <Text style={[s.waitText, on && { color: colors.white }]}>{m}m</Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  </View>
                </View>

                {/* Where it goes */}
                <View style={[s.card, s.dropCard]}>
                  <MapThumb />
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <TextInput
                      value={dropLabel}
                      onChangeText={setDropLabel}
                      placeholder="Deliver to my location"
                      placeholderTextColor={colors.ink}
                      style={s.dropInput}
                      maxLength={120}
                      accessibilityLabel="Room or landmark"
                    />
                    <Text style={s.coords}>
                      {locating
                        ? "Finding you…"
                        : drop
                          ? `${drop.lat.toFixed(5)}, ${drop.lng.toFixed(5)}`
                          : "Location unavailable, enable location access to post."}
                    </Text>
                  </View>
                  <Icon name="pin" size={18} color={drop ? colors.brand : colors.caution} />
                </View>
                <Text style={s.hint}>
                  Add a room or landmark above so the runner knows exactly where to come.
                </Text>
              </Section>

              {error ? <ErrorNote>{error}</ErrorNote> : null}
            </>
          )}
        </ScrollView>

        {/* Footer: a running total on step one, the itemised hold on step two. */}
        <View style={s.footer}>
          {step === 1 ? (
            <>
              <View style={s.footSummary}>
                <Icon name={isShopping ? "bag" : "parcel"} size={17} color={colors.brand} />
                <Text style={s.footText}>
                  {isShopping
                    ? `${rows.length} line${rows.length === 1 ? "" : "s"} on your list`
                    : chosenCourier
                      ? `${chosenCourier} pickup`
                      : "Choose who it is from"}
                </Text>
                {isShopping && pricedTotal > 0 ? (
                  <Text style={s.footValue}>{money(pricedTotal)}</Text>
                ) : null}
              </View>
              <Button
                title="Reward and delivery"
                size="lg"
                icon="chev"
                iconRight
                disabled={!stepOneReady}
                onPress={() => setStep(2)}
              />
            </>
          ) : (
            <>
              <View style={{ gap: 7 }}>
                {isShopping ? (
                  <BillLine label="Items estimate" value={money(pricedTotal)} />
                ) : null}
                {collectNum > 0 ? <BillLine label="Cash at pickup" value={money(collectNum)} /> : null}
                <BillLine label="Runner reward" value={money(reward)} />
                {buffer != null && buffer > 0 ? (
                  <BillLine label="Price buffer, unspent comes back" value={money(buffer)} />
                ) : null}
                {unpriced > 0 ? (
                  <BillLine
                    label={`${unpriced} unlisted line${unpriced === 1 ? "" : "s"}, reported by the runner`}
                    value="—"
                  />
                ) : null}
              </View>
              <View style={s.holdRow}>
                <Icon name="lock" size={17} color={colors.brand} />
                <Text style={s.holdLabel}>Held in escrow now</Text>
                <Text style={s.holdValue}>{hold != null ? money(hold) : "—"}</Text>
              </View>
              <Button
                title="Post errand"
                size="lg"
                icon="chev"
                iconRight
                loading={create.isPending}
                disabled={!ready}
                onPress={submit}
              />
              <Text style={s.footCaption}>
                Goes to your friends and their friends first, for {FRIENDS_FIRST_SECONDS} seconds
              </Text>
            </>
          )}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Section({
  n,
  title,
  right,
  children,
}: {
  n: number;
  title: string;
  right?: string;
  children: React.ReactNode;
}) {
  return (
    <View style={{ gap: 10 }}>
      <View style={s.sectionHead}>
        <View style={s.sectionNum}>
          <Text style={s.sectionNumText}>{n}</Text>
        </View>
        <Text style={s.sectionTitle}>{title}</Text>
        {right ? <Text style={s.sectionRight}>{right}</Text> : null}
      </View>
      {children}
    </View>
  );
}

function BillLine({ label, value }: { label: string; value: string }) {
  return (
    <View style={s.billLine}>
      <Text style={s.billLabel}>{label}</Text>
      <Text style={s.billValue}>{value}</Text>
    </View>
  );
}

/** The little drawn map tile beside the drop-off, as the design draws it. */
function MapThumb() {
  return (
    <View style={s.mapThumb}>
      <Svg width={44} height={44} viewBox="0 0 44 44">
        <Rect width={44} height={44} fill={colors.mapBg} />
        <Path d="M-2 16H46M-2 30H46M14 -2V46M30 -2V46" stroke={colors.mapLine} strokeWidth={3} />
        <Circle cx={22} cy={22} r={5} fill={colors.brand} />
      </Svg>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.white },

  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 4,
  },
  headBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
  },
  headTitle: { color: colors.ink, fontSize: 16, fontFamily: font.black, letterSpacing: -0.4 },
  headSub: { color: colors.mutedCool, fontSize: 11.5, fontFamily: font.regular },

  scroll: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: space.xl, gap: 20 },

  sectionHead: { flexDirection: "row", alignItems: "center", gap: 8 },
  sectionNum: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
  sectionNumText: { color: colors.white, fontSize: 10.5, fontFamily: font.black },
  sectionTitle: { color: colors.ink, fontSize: 13.5, fontFamily: font.bold },
  sectionRight: { marginLeft: "auto", color: colors.mutedCool, fontSize: 11.5, fontFamily: font.regular },

  segment: { flexDirection: "row", padding: 4, borderRadius: radius.md, backgroundColor: colors.chip, gap: 4 },
  segItem: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    height: 38,
    borderRadius: 11,
  },
  segItemOn: {
    backgroundColor: colors.white,
    shadowColor: colors.ink,
    shadowOpacity: 0.12,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  segText: { color: colors.mutedCool, fontSize: 12, fontFamily: font.bold },

  lines: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.xl,
    overflow: "hidden",
  },
  line: { flexDirection: "row", alignItems: "center", gap: 11, paddingHorizontal: 14, paddingVertical: 12 },
  lineDivider: { borderTopWidth: 1, borderTopColor: colors.hairlineSoft },
  lineIcon: {
    width: 34,
    height: 34,
    borderRadius: 11,
    backgroundColor: colors.brandTint,
    alignItems: "center",
    justifyContent: "center",
  },
  lineName: { color: colors.ink, fontSize: 13.5, fontFamily: font.semi },
  listedRow: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 1 },
  listed: { color: colors.credit, fontSize: 10.5, fontFamily: font.regular },
  unlisted: { color: colors.mutedCool, fontSize: 10.5, fontFamily: font.regular, marginTop: 1 },
  stepper: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.sm,
    height: 34,
  },
  stepBtn: { paddingHorizontal: 8, height: "100%", justifyContent: "center" },
  stepValue: { color: colors.ink, fontSize: 13, fontFamily: font.bold, minWidth: 12, textAlign: "center" },
  lineTotal: { color: colors.ink, fontSize: 13, fontFamily: font.bold, width: 30, textAlign: "right" },

  hint: { color: colors.muted, fontSize: 12, fontFamily: font.regular, lineHeight: 18 },

  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
  },
  chipOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  chipText: { color: colors.inkSoft, fontSize: 12.5, fontFamily: font.bold },

  handoff: {
    gap: 14,
    padding: 14,
    borderRadius: radius.xl,
    backgroundColor: colors.bgSoft,
    borderWidth: 1,
    borderColor: colors.hairline,
  },
  handoffHead: { flexDirection: "row", alignItems: "flex-start", gap: 9 },
  handoffNote: { flex: 1, color: colors.muted, fontSize: 12, fontFamily: font.regular, lineHeight: 18 },

  summary: {
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    padding: 14,
    borderRadius: radius.xl,
    backgroundColor: colors.bgSoft,
    borderWidth: 1,
    borderColor: colors.hairline,
  },
  summaryTitle: { color: colors.ink, fontSize: 13, fontFamily: font.bold },
  summarySub: { color: colors.muted, fontSize: 11, fontFamily: font.regular, marginTop: 1 },
  link: { color: colors.brand, fontSize: 12, fontFamily: font.bold },

  card: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.xl,
    padding: 14,
  },
  rewardLabel: { color: colors.muted, fontSize: 11.5, fontFamily: font.regular },
  rewardRow: { flexDirection: "row", alignItems: "baseline", gap: 4, marginTop: 2 },
  rewardRupee: { color: colors.mutedCool, fontSize: 17, fontFamily: font.bold },
  rewardValue: { color: colors.ink, fontSize: 26, fontFamily: font.black, letterSpacing: -0.8 },
  rewardInput: {
    minWidth: 60,
    color: colors.ink,
    fontSize: 26,
    fontFamily: font.black,
    letterSpacing: -0.8,
    padding: 0,
  },
  presets: { flexDirection: "row", gap: 8, marginTop: 13 },
  preset: {
    flex: 1,
    height: 42,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.line,
    alignItems: "center",
    justifyContent: "center",
  },
  presetOn: { borderWidth: 1.5, borderColor: colors.brand, backgroundColor: colors.brandWash },
  presetText: { color: colors.muted, fontSize: 13, fontFamily: font.bold },
  presetTextOn: { color: colors.brand, fontFamily: font.black },
  presetCustom: {
    width: 52,
    height: 42,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: colors.lineOutline,
    alignItems: "center",
    justifyContent: "center",
  },
  waitRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginTop: 14,
    paddingTop: 14,
    borderTopWidth: 1,
    borderTopColor: colors.hairlineSoft,
  },
  waitLabel: { color: colors.inkSoft, fontSize: 12, fontFamily: font.regular },
  waitPills: { flexDirection: "row", gap: 6, marginLeft: "auto" },
  waitPill: {
    paddingHorizontal: 11,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.line,
  },
  waitPillOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  waitText: { color: colors.muted, fontSize: 11.5, fontFamily: font.bold },

  dropCard: { flexDirection: "row", alignItems: "center", gap: 11, marginTop: 6 },
  mapThumb: { width: 44, height: 44, borderRadius: radius.md, overflow: "hidden" },
  dropInput: { color: colors.ink, fontSize: 13.5, fontFamily: font.bold, padding: 0 },
  coords: { color: colors.mutedCool, fontSize: 10.5, fontFamily: font.mono, marginTop: 2 },

  footer: {
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
    backgroundColor: colors.white,
    paddingHorizontal: 20,
    paddingTop: 14,
    paddingBottom: 14,
    shadowColor: colors.ink,
    shadowOpacity: 0.1,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: -8 },
    elevation: 8,
  },
  footSummary: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 12 },
  footText: { color: colors.muted, fontSize: 12.5, fontFamily: font.regular },
  footValue: { marginLeft: "auto", color: colors.ink, fontSize: 15, fontFamily: font.black },

  billLine: { flexDirection: "row", alignItems: "center", gap: 10 },
  billLabel: { flex: 1, color: colors.muted, fontSize: 11.5, fontFamily: font.regular },
  billValue: { color: colors.inkSoft, fontSize: 11.5, fontFamily: font.semi },
  holdRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginVertical: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderStyle: "dashed",
    borderTopColor: colors.line,
  },
  holdLabel: { color: colors.ink, fontSize: 12.5, fontFamily: font.bold },
  holdValue: { marginLeft: "auto", color: colors.ink, fontSize: 19, fontFamily: font.black, letterSpacing: -0.5 },
  footCaption: {
    color: colors.mutedCool,
    fontSize: 11,
    fontFamily: font.regular,
    textAlign: "center",
    marginTop: 9,
  },
});
