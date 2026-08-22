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
import { apiErrorMessage } from "../../src/lib/api";
import { categoryIcon, colors, font, radius, space } from "../../src/theme";

const CATEGORIES: { value: Category; label: string }[] = [
  { value: "FOOD", label: "Food" },
  { value: "GROCERY", label: "Grocery" },
  { value: "STATIONERY", label: "Stationery" },
  { value: "PHARMACY", label: "Pharmacy" },
  { value: "PARCEL", label: "Parcel" },
  { value: "CUSTOM", label: "Main gate" },
];

/** Backend derives fulfillment from category; these two need handoff details. */
const PICKUP_CATEGORIES: Category[] = ["CUSTOM", "PARCEL"];
const WAIT_OPTIONS = [15, 30, 45, 60];
const REWARD_PRESETS = [10, 20, 30, 50];

export default function NewErrand() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const params = useLocalSearchParams<{ category?: Category; mode?: string }>();

  const [category, setCategory] = useState<Category>(
    params.category ?? (params.mode === "shopping" ? "GROCERY" : "FOOD"),
  );
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [pickup, setPickup] = useState("");
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
  const ready = title.trim().length >= 3 && pickup.trim().length >= 2 && !!drop;

  function submit() {
    if (!drop) return;
    setError(null);
    create.mutate({
      category,
      title: title.trim(),
      notes: notes.trim() || undefined,
      pickup_label: pickup.trim(),
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
            <Pressable onPress={() => router.back()} style={s.close} hitSlop={12}>
              <Text style={s.closeGlyph}>✕</Text>
            </Pressable>
          </Row>

          <Title style={{ marginTop: space.sm }}>New errand</Title>
          <Body muted style={{ marginTop: space.xs }}>
            Tell a runner what you need and what it's worth.
          </Body>

          {/* Category */}
          <Label style={{ marginTop: space.xxl, marginBottom: space.md }}>Category</Label>
          <Row gap={space.sm} wrap>
            {CATEGORIES.map((c) => {
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

          <View style={{ gap: space.lg, marginTop: space.xxl }}>
            <Field
              label="What do you need?"
              placeholder="2 veg rolls and a cold coffee"
              value={title}
              onChangeText={setTitle}
              maxLength={200}
            />

            <Field
              label="Pick up from"
              placeholder={isPickup ? "Main Gate" : "Foodys Express"}
              value={pickup}
              onChangeText={setPickup}
              maxLength={200}
            />

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
                  style={{ flex: 1 }}
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
