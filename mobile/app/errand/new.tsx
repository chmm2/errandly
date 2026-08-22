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
import { categoryStyle, colors, font, radius, space } from "../../src/theme";

const CATEGORIES: Category[] = ["FOOD", "GROCERY", "PARCEL", "STATIONERY", "PHARMACY", "CUSTOM"];
/** Backend derives fulfillment from category; these two need handoff details. */
const PICKUP_CATEGORIES: Category[] = ["CUSTOM", "PARCEL"];
const WAIT_OPTIONS = [15, 30, 45, 60];

export default function NewErrand() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const params = useLocalSearchParams<{ category?: Category }>();

  const [category, setCategory] = useState<Category>(params.category ?? "FOOD");
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
  const ready = title.trim().length >= 3 && pickup.trim().length >= 2 && !!drop && rewardNum >= 0;

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
          <Row justify="space-between" style={{ marginBottom: space.lg }}>
            <Pressable onPress={() => router.back()} style={s.close} hitSlop={12}>
              <Text style={s.closeGlyph}>✕</Text>
            </Pressable>
          </Row>

          <Title>New errand</Title>
          <Body dim style={{ marginTop: space.xs }}>
            Tell a runner what you need and what it's worth.
          </Body>

          {/* Category */}
          <Label style={{ marginTop: space.xl, marginBottom: space.sm }}>Category</Label>
          <Row gap={space.sm} wrap>
            {CATEGORIES.map((c) => {
              const cat = categoryStyle[c];
              const on = c === category;
              return (
                <Pressable
                  key={c}
                  onPress={() => setCategory(c)}
                  style={[
                    s.cat,
                    { borderColor: on ? cat.color : colors.border },
                    on && { backgroundColor: cat.tint },
                  ]}
                >
                  <Text style={{ fontSize: 18 }}>{cat.emoji}</Text>
                  <Caption style={{ color: on ? cat.color : colors.textDim, fontWeight: font.semi }}>
                    {cat.label}
                  </Caption>
                </Pressable>
              );
            })}
          </Row>

          <View style={{ gap: space.md, marginTop: space.xl }}>
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
              numberOfLines={3}
              style={{ minHeight: 84, textAlignVertical: "top" }}
              maxLength={2000}
            />

            {/* Reward */}
            <View style={{ gap: space.xs }}>
              <Label>Reward for the runner</Label>
              <Row gap={space.sm}>
                <Field
                  value={reward}
                  onChangeText={setReward}
                  keyboardType="number-pad"
                  style={{ flex: 1 }}
                  placeholder="20"
                />
                {[10, 20, 30, 50].map((v) => (
                  <Pressable key={v} onPress={() => setReward(String(v))} style={s.preset}>
                    <Caption style={{ color: colors.text, fontWeight: font.bold }}>₹{v}</Caption>
                  </Pressable>
                ))}
              </Row>
            </View>

            {/* Wait window */}
            <View style={{ gap: space.xs }}>
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
                          color: on ? colors.brandBright : colors.textDim,
                          fontWeight: font.bold,
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
              <Card style={{ gap: space.md, backgroundColor: colors.surfaceHigh }}>
                <Row gap={space.sm}>
                  <Text style={{ fontSize: 15 }}>🔐</Text>
                  <Body style={{ fontWeight: font.bold, flex: 1 }}>Handoff details</Body>
                </Row>
                <Caption style={{ marginTop: -space.sm }}>
                  Shared only with the runner who accepts, and every view is logged.
                </Caption>
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
            <Card style={{ backgroundColor: colors.surfaceHigh }}>
              <Row gap={space.sm} align="flex-start">
                <Text style={{ fontSize: 15 }}>📍</Text>
                <View style={{ flex: 1 }}>
                  <Body style={{ fontWeight: font.bold }}>Deliver to my location</Body>
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
              style={{ marginTop: space.sm }}
            />
            {!drop && !locating ? (
              <Caption style={{ textAlign: "center", color: colors.danger }}>
                A drop location is required.
              </Caption>
            ) : null}
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
    borderRadius: 20,
    backgroundColor: colors.surfaceHigh,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
    marginLeft: "auto",
  },
  closeGlyph: { color: colors.text, fontSize: 15, fontWeight: font.bold },

  cat: {
    width: "31.5%",
    paddingVertical: space.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    backgroundColor: colors.surface,
    alignItems: "center",
    gap: 5,
  },

  preset: {
    paddingHorizontal: space.md,
    height: 50,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceHigh,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },

  wait: {
    flex: 1,
    paddingVertical: space.md,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
  },
  waitOn: { borderColor: colors.brand, backgroundColor: "rgba(124,92,255,0.14)" },
});
