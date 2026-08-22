import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";

import {
  cancelErrand,
  completeErrand,
  deliverErrand,
  type Errand,
  fetchErrand,
  fetchErrandEvents,
  fetchHandoffSecret,
  type HandoffSecret,
  pickupErrand,
  rateErrand,
  releaseErrand,
  setItemAvailability,
} from "../../src/api/errands";
import { ChatPanel } from "../../src/components/ChatPanel";
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
import { useSocket } from "../../src/lib/ws";
import { useAuth } from "../../src/stores/auth";
import {
  categoryStyle,
  colors,
  font,
  metres,
  radius,
  rupees,
  shadow,
  space,
  statusStyle,
  timeAgo,
} from "../../src/theme";

const LIVE: Errand["status"][] = ["ACCEPTED", "IN_PROGRESS", "DELIVERED"];

/** The happy path, in order — drives the progress rail. */
const STEPS: { status: Errand["status"]; label: string }[] = [
  { status: "OPEN", label: "Posted" },
  { status: "ACCEPTED", label: "Runner assigned" },
  { status: "IN_PROGRESS", label: "Picked up" },
  { status: "DELIVERED", label: "Delivered" },
  { status: "COMPLETED", label: "Confirmed" },
];

export default function ErrandDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const myId = useAuth((s) => s.user?.id);

  const [runnerPos, setRunnerPos] = useState<{ lat: number; lng: number } | null>(null);
  const [secret, setSecret] = useState<HandoffSecret | null>(null);
  const [stars, setStars] = useState(0);

  const { data: errand, isLoading } = useQuery({
    queryKey: ["errand", id],
    queryFn: () => fetchErrand(id!),
    enabled: !!id,
    refetchInterval: 30_000,
  });

  const { data: events } = useQuery({
    queryKey: ["errand-events", id],
    queryFn: () => fetchErrandEvents(id!),
    enabled: !!id,
  });

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["errand", id] });
    queryClient.invalidateQueries({ queryKey: ["errand-events", id] });
    queryClient.invalidateQueries({ queryKey: ["my-errands"] });
  }, [queryClient, id]);

  // One socket carries status transitions, runner location, and chat.
  useSocket(
    errand && LIVE.includes(errand.status) ? `/ws/errands/${id}` : null,
    useCallback(
      (data: Record<string, unknown>) => {
        if (data.type === "location") {
          setRunnerPos({ lat: data.lat as number, lng: data.lng as number });
        } else if (data.type !== "chat") {
          invalidate();
        }
      },
      [invalidate],
    ),
  );

  const pickup = useMutation({
    mutationFn: () => pickupErrand(id!),
    onSuccess: invalidate,
    onError: (err) => Alert.alert("Couldn't mark picked up", apiErrorMessage(err)),
  });
  const deliver = useMutation({
    mutationFn: () => deliverErrand(id!),
    onSuccess: invalidate,
    onError: (err) => Alert.alert("Couldn't mark delivered", apiErrorMessage(err)),
  });
  const complete = useMutation({
    mutationFn: () => completeErrand(id!),
    onSuccess: invalidate,
    onError: (err) => Alert.alert("Couldn't confirm", apiErrorMessage(err)),
  });
  const release = useMutation({
    mutationFn: () => releaseErrand(id!),
    onSuccess: invalidate,
    onError: (err) => Alert.alert("Couldn't release", apiErrorMessage(err)),
  });

  const cancel = useMutation({
    mutationFn: (reason?: string) => cancelErrand(id!, reason),
    onSuccess: invalidate,
    onError: (err) => Alert.alert("Couldn't cancel", apiErrorMessage(err)),
  });

  const toggleItem = useMutation({
    mutationFn: (v: { itemId: string; available: boolean }) =>
      setItemAvailability(id!, v.itemId, v.available),
    onSuccess: invalidate,
    onError: (err) => Alert.alert("Couldn't update item", apiErrorMessage(err)),
  });

  const rate = useMutation({
    mutationFn: (n: number) => rateErrand(id!, n),
    onSuccess: invalidate,
    onError: (err) => Alert.alert("Couldn't submit rating", apiErrorMessage(err)),
  });

  if (isLoading || !errand) {
    return (
      <Screen>
        <Loading label="Loading errand…" />
      </Screen>
    );
  }

  const isRequester = errand.requester_id === myId;
  const isRunner = errand.runner_id === myId;
  const cat = categoryStyle[errand.category];
  const status = statusStyle[errand.status];
  const stepIndex = STEPS.findIndex((s) => s.status === errand.status);
  const terminal = ["CANCELLED", "EXPIRED"].includes(errand.status);

  async function revealSecret() {
    try {
      setSecret(await fetchHandoffSecret(id!));
    } catch (err) {
      Alert.alert("Couldn't reveal code", apiErrorMessage(err));
    }
  }

  return (
    <Screen scroll>
      {/* Header */}
      <Row justify="space-between" style={{ paddingTop: space.md }}>
        <Pressable onPress={() => router.back()} style={s.back} hitSlop={12}>
          <Text style={s.backGlyph}>←</Text>
        </Pressable>
        <Chip label={status.label} color={status.color} tint={status.tint} />
      </Row>

      <Row gap={space.sm} style={{ marginTop: space.lg }}>
        <Chip label={cat.label} icon={cat.emoji} color={cat.color} tint={cat.tint} />
      </Row>

      <Heading style={{ marginTop: space.sm }}>{errand.title}</Heading>

      <Row gap={space.md} wrap style={{ marginTop: space.sm }}>
        <Text style={s.reward}>{rupees(errand.reward)}</Text>
        <Caption>reward</Caption>
        {errand.collect_amount > 0 ? (
          <Caption style={{ color: colors.warning }}>
            + {rupees(errand.collect_amount)} reimbursed
          </Caption>
        ) : null}
      </Row>

      {/* Progress rail */}
      {!terminal ? (
        <Card style={{ marginTop: space.xl }}>
          {STEPS.map((step, i) => {
            const done = stepIndex >= i;
            const current = stepIndex === i;
            return (
              <Row key={step.status} gap={space.md} align="flex-start">
                <View style={{ alignItems: "center", width: 22 }}>
                  <View
                    style={[
                      s.node,
                      done && { backgroundColor: status.color, borderColor: status.color },
                      current && shadow.glow(status.color),
                    ]}
                  >
                    {done ? <Text style={s.tick}>✓</Text> : null}
                  </View>
                  {i < STEPS.length - 1 ? (
                    <View
                      style={[s.rail, stepIndex > i && { backgroundColor: status.color }]}
                    />
                  ) : null}
                </View>
                <View style={{ flex: 1, paddingBottom: i < STEPS.length - 1 ? space.lg : 0 }}>
                  <Body
                    style={{
                      fontWeight: current ? font.bold : font.regular,
                      color: done ? colors.text : colors.textFaint,
                    }}
                  >
                    {step.label}
                  </Body>
                </View>
              </Row>
            );
          })}
        </Card>
      ) : null}

      {/* Runner card */}
      {errand.runner ? (
        <Card style={{ marginTop: space.lg }}>
          <Label>Your runner</Label>
          <Row gap={space.md} style={{ marginTop: space.md }}>
            <View style={s.runnerAvatar}>
              <Text style={{ fontSize: 20 }}>🛵</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Body style={{ fontWeight: font.bold }}>{errand.runner.display_name}</Body>
              <Caption>
                ⭐ {errand.runner.reputation_score.toFixed(2)} · {errand.runner.trips_completed}{" "}
                trips
              </Caption>
            </View>
            {errand.runner.phone ? (
              <Chip label={errand.runner.phone} color={colors.success} tint="rgba(47,217,143,0.14)" />
            ) : null}
          </Row>

          {runnerPos ? (
            <View style={s.livePos}>
              <Row gap={space.sm}>
                <View style={s.pulse} />
                <Caption style={{ color: colors.success }}>
                  Live · {runnerPos.lat.toFixed(5)}, {runnerPos.lng.toFixed(5)}
                </Caption>
              </Row>
            </View>
          ) : errand.runner_lat != null ? (
            <Caption style={{ marginTop: space.md }}>
              Last seen at {errand.runner_lat.toFixed(5)}, {errand.runner_lng?.toFixed(5)}
            </Caption>
          ) : null}
        </Card>
      ) : null}

      {/* Order items */}
      {errand.items.length > 0 ? (
        <Card style={{ marginTop: space.lg }}>
          <Row justify="space-between">
            <Label>Order</Label>
            <Caption style={{ color: colors.text, fontWeight: font.bold }}>
              {rupees(errand.items_total)}
            </Caption>
          </Row>
          <View style={{ marginTop: space.md, gap: space.sm }}>
            {errand.items.map((item) => (
              <Row key={item.id} justify="space-between" gap={space.md}>
                <View style={{ flex: 1 }}>
                  <Body
                    style={{
                      textDecorationLine: item.is_available ? "none" : "line-through",
                      color: item.is_available ? colors.text : colors.textFaint,
                    }}
                  >
                    {item.quantity}× {item.name_snapshot}
                  </Body>
                  {item.note ? <Caption>{item.note}</Caption> : null}
                </View>

                {isRunner && ["ACCEPTED", "IN_PROGRESS"].includes(errand.status) ? (
                  <Pressable
                    onPress={() =>
                      toggleItem.mutate({ itemId: item.id, available: !item.is_available })
                    }
                    style={s.stockBtn}
                  >
                    <Caption
                      style={{
                        color: item.is_available ? colors.danger : colors.success,
                        fontWeight: font.bold,
                      }}
                    >
                      {item.is_available ? "Out of stock" : "Restore"}
                    </Caption>
                  </Pressable>
                ) : item.unit_price_snapshot != null ? (
                  <Caption>{rupees(item.unit_price_snapshot * item.quantity)}</Caption>
                ) : null}
              </Row>
            ))}
          </View>
        </Card>
      ) : null}

      {/* Handoff secret — runner only */}
      {isRunner && errand.has_handoff_secret && LIVE.includes(errand.status) ? (
        <Card style={{ marginTop: space.lg, borderColor: colors.borderBright }}>
          <Row gap={space.sm}>
            <Text style={{ fontSize: 15 }}>🔐</Text>
            <Label>Handoff details</Label>
          </Row>
          {secret ? (
            <View style={{ marginTop: space.md, gap: space.xs }}>
              {secret.otp ? <Text style={s.secretCode}>{secret.otp}</Text> : null}
              {secret.external_ref ? (
                <Caption>Order ref: {secret.external_ref}</Caption>
              ) : null}
              {secret.collect_amount > 0 ? (
                <Caption style={{ color: colors.warning }}>
                  Pay {rupees(secret.collect_amount)} at pickup — reimbursed on completion.
                </Caption>
              ) : null}
            </View>
          ) : (
            <>
              <Caption style={{ marginTop: space.xs, marginBottom: space.md }}>
                Viewing is recorded on the errand's audit trail.
              </Caption>
              <Button title="Reveal code" variant="surface" onPress={revealSecret} />
            </>
          )}
        </Card>
      ) : null}

      {/* Actions */}
      <View style={{ marginTop: space.xl, gap: space.sm }}>
        {isRunner && errand.status === "ACCEPTED" ? (
          <>
            <Button
              title="Mark picked up"
              size="lg"
              loading={pickup.isPending}
              onPress={() => pickup.mutate()}
            />
            <Button
              title="Hand back to queue"
              variant="surface"
              loading={release.isPending}
              onPress={() => release.mutate()}
            />
          </>
        ) : null}

        {isRunner && errand.status === "IN_PROGRESS" ? (
          <Button
            title="Mark delivered"
            size="lg"
            variant="gold"
            loading={deliver.isPending}
            onPress={() => deliver.mutate()}
          />
        ) : null}

        {isRequester && errand.status === "DELIVERED" ? (
          <Button
            title="Confirm handoff"
            size="lg"
            loading={complete.isPending}
            onPress={() => complete.mutate()}
          />
        ) : null}

        {isRequester && ["OPEN", "ACCEPTED"].includes(errand.status) ? (
          <Button
            title="Cancel errand"
            variant="danger"
            loading={cancel.isPending}
            onPress={() =>
              Alert.alert("Cancel this errand?", "The runner will be told it's off.", [
                { text: "Keep it", style: "cancel" },
                {
                  text: "Cancel errand",
                  style: "destructive",
                  onPress: () => cancel.mutate(undefined),
                },
              ])
            }
          />
        ) : null}
      </View>

      {/* Rating */}
      {isRequester && errand.status === "COMPLETED" && !errand.rated ? (
        <Card style={{ marginTop: space.xl }} glow={colors.gold}>
          <Label>Rate your runner</Label>
          <Row gap={space.sm} justify="center" style={{ marginVertical: space.lg }}>
            {[1, 2, 3, 4, 5].map((n) => (
              <Pressable key={n} onPress={() => setStars(n)} hitSlop={6}>
                <Text style={{ fontSize: 32, opacity: n <= stars ? 1 : 0.28 }}>⭐</Text>
              </Pressable>
            ))}
          </Row>
          <Button
            title="Submit rating"
            disabled={stars === 0}
            loading={rate.isPending}
            onPress={() => rate.mutate(stars)}
          />
        </Card>
      ) : null}

      {/* Chat */}
      {errand.runner_id && (isRequester || isRunner) ? (
        <ChatPanel errandId={errand.id} />
      ) : null}

      {/* Audit trail */}
      {events && events.length > 0 ? (
        <>
          <Label style={{ marginTop: space.xxl, marginBottom: space.sm }}>History</Label>
          <Card style={{ gap: space.sm }}>
            {events.map((e) => (
              <Row key={e.id} justify="space-between" gap={space.md}>
                <Caption style={{ color: colors.text, flex: 1 }}>
                  {e.event_type.replaceAll("_", " ").toLowerCase()}
                </Caption>
                <Caption>{timeAgo(e.created_at)}</Caption>
              </Row>
            ))}
          </Card>
        </>
      ) : null}
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

  reward: { color: colors.gold, fontSize: 28, fontWeight: font.black, letterSpacing: -0.8 },

  node: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: colors.borderBright,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  tick: { color: "#0B0F1A", fontSize: 11, fontWeight: font.black },
  rail: { width: 2, flex: 1, minHeight: 26, backgroundColor: colors.border, marginVertical: 2 },

  runnerAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.surfaceHigh,
    alignItems: "center",
    justifyContent: "center",
  },
  livePos: {
    marginTop: space.md,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  pulse: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success },

  stockBtn: {
    paddingHorizontal: space.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceHigh,
    borderWidth: 1,
    borderColor: colors.border,
  },

  secretCode: {
    color: colors.text,
    fontSize: 30,
    fontWeight: font.black,
    letterSpacing: 8,
  },
});
