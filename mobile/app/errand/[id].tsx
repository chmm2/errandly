import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

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
import { FindingRunner } from "../../src/components/CountdownRing";
import { ConnectionBadge, ConnectionLine } from "../../src/components/ConnectionBadge";
import { PriceClaimSheet } from "../../src/components/PriceClaimSheet";
import { PaymentSummary } from "../../src/components/PaymentSummary";
import { TrackingMap } from "../../src/components/TrackingMap";
import {
  Body,
  Button,
  Caption,
  Card,
  EmptyState,
  Heading,
  Hero,
  IconTile,
  Loading,
  Pill,
  Row,
  Screen,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { confirm, notify } from "../../src/lib/dialog";
import { useSocket } from "../../src/lib/ws";
import { goBack } from "../../src/lib/nav";
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

/**
 * Statuses worth holding a socket open for. OPEN belongs here: waiting for a
 * runner is exactly when you want the accept to land without a refresh, and
 * leaving it out meant the one state that most needed live updates was the one
 * state that never subscribed.
 */
const LIVE: Errand["status"][] = ["OPEN", "ACCEPTED", "IN_PROGRESS", "DELIVERED"];

/** Runner is assigned and moving — show their card and position. */
const ASSIGNED: Errand["status"][] = ["ACCEPTED", "IN_PROGRESS", "DELIVERED"];

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

  const {
    data: errand,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
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
    onError: (err) => notify("Couldn't mark picked up", apiErrorMessage(err)),
  });
  const deliver = useMutation({
    mutationFn: () => deliverErrand(id!),
    onSuccess: invalidate,
    onError: (err) => notify("Couldn't mark delivered", apiErrorMessage(err)),
  });
  const complete = useMutation({
    mutationFn: () => completeErrand(id!),
    onSuccess: invalidate,
    onError: (err) => notify("Couldn't confirm", apiErrorMessage(err)),
  });
  const release = useMutation({
    mutationFn: () => releaseErrand(id!),
    onSuccess: invalidate,
    onError: (err) => notify("Couldn't release", apiErrorMessage(err)),
  });
  const cancel = useMutation({
    mutationFn: (reason?: string) => cancelErrand(id!, reason),
    onSuccess: invalidate,
    onError: (err) => notify("Couldn't cancel", apiErrorMessage(err)),
  });
  const toggleItem = useMutation({
    mutationFn: (v: { itemId: string; available: boolean }) =>
      setItemAvailability(id!, v.itemId, v.available),
    onSuccess: invalidate,
    onError: (err) => notify("Couldn't update item", apiErrorMessage(err)),
  });
  const rate = useMutation({
    mutationFn: (n: number) => rateErrand(id!, n),
    onSuccess: invalidate,
    onError: (err) => notify("Couldn't submit rating", apiErrorMessage(err)),
  });

  // A failed fetch must never render as loading. The previous condition was
  // `isLoading || !errand`, so any error — an expired token, a dropped
  // connection, a 404 — left the spinner up forever with nothing to act on.
  if (isError || (!isLoading && !errand)) {
    return (
      <Screen>
        <Pressable onPress={() => goBack(router)} style={s.backBtn} hitSlop={12}>
          <Text style={s.backGlyph}>←</Text>
        </Pressable>
        <EmptyState
          emoji="😕"
          title="Couldn't load this errand"
          body={error ? apiErrorMessage(error) : "It may have been removed, or the link is wrong."}
          action={<Button title="Try again" onPress={() => refetch()} />}
        />
      </Screen>
    );
  }

  if (isLoading || !errand) {
    return (
      <Screen>
        <Loading label="Loading errand…" />
      </Screen>
    );
  }

  const isRequester = errand.requester_id === myId;
  const isRunner = errand.runner_id === myId;
  const status = statusStyle[errand.status];
  const stepIndex = STEPS.findIndex((st) => st.status === errand.status);
  const terminal = ["CANCELLED", "EXPIRED"].includes(errand.status);

  async function revealSecret() {
    try {
      setSecret(await fetchHandoffSecret(id!));
    } catch (err) {
      notify("Couldn't reveal code", apiErrorMessage(err));
    }
  }

  return (
    <Screen scroll padded={false}>
      <Hero compact onBack={() => goBack(router)} title={errand.title}>
        <Row gap={space.md} style={{ marginTop: space.md }} wrap>
          <Text style={s.reward}>{rupees(errand.reward)}</Text>
          <Text style={s.rewardLabel}>reward</Text>
          {errand.collect_amount > 0 ? (
            <Text style={s.rewardLabel}>+ {rupees(errand.collect_amount)} reimbursed</Text>
          ) : null}
        </Row>
      </Hero>

      <View style={{ paddingHorizontal: space.lg, paddingTop: space.xl }}>
        <Row justify="flex-end">
          <Pill label={status.label} bg={status.bg} color={status.text} />
        </Row>

        <Row gap={space.md} style={{ marginTop: space.lg }}>
          <IconTile emoji={categoryIcon[errand.category] ?? "✨"} />
          <View style={{ flex: 1 }}>
            <Caption numberOfLines={2}>
              from {errand.pickup_label}
              {errand.drop_label ? ` → ${errand.drop_label}` : ""}
            </Caption>
            {errand.notes ? (
              <Caption style={{ marginTop: 2 }} numberOfLines={3}>
                “{errand.notes}”
              </Caption>
            ) : null}
          </View>
        </Row>

        {/* The other direction: a runner looking at someone else's errand sees
            how they connect to whoever posted it. This is the deciding fact
            when choosing which run to take, so it sits above the fold rather
            than in the payment block at the bottom. */}
        {!isRequester && errand.connection ? (
          <Card style={{ marginTop: space.lg }}>
            <ConnectionLine connection={errand.connection} />
          </Card>
        ) : null}

        {/* Waiting for a runner. Requester-only: this is *their* deadline
            ticking down. A runner browsing the same errand has no stake in it
            and shouldn't be shown the poster's private countdown. */}
        {isRequester && errand.status === "OPEN" && errand.expires_at ? (
          <FindingRunner createdAt={errand.created_at} expiresAt={errand.expires_at} />
        ) : null}

        {/* Progress rail. Both parties, nobody else: a runner browsing open
            work is deciding whether to take it, and where somebody else's
            errand has got to is not part of that decision. The backend now
            refuses non-parties a non-open errand outright, so this is the
            second lock rather than the only one. */}
        {!terminal && (isRequester || isRunner) ? (
          <Card raised style={{ marginTop: space.xl }}>
            {STEPS.map((step, i) => {
              const done = stepIndex >= i;
              const current = stepIndex === i;
              return (
                <Row key={step.status} gap={space.md} align="flex-start">
                  <View style={{ alignItems: "center", width: 22 }}>
                    <View
                      style={[
                        s.node,
                        done && { backgroundColor: colors.brand, borderColor: colors.brand },
                      ]}
                    >
                      {done ? <Text style={s.tick}>✓</Text> : null}
                    </View>
                    {i < STEPS.length - 1 ? (
                      <View style={[s.rail, stepIndex > i && { backgroundColor: colors.brand }]} />
                    ) : null}
                  </View>
                  <View style={{ flex: 1, paddingBottom: i < STEPS.length - 1 ? space.lg : 0 }}>
                    <Body
                      style={{
                        fontFamily: current ? font.bold : font.regular,
                        color: done ? colors.ink : colors.muted,
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

        {/* Live map — requester's tracking view, only while someone is
            actually on the way. */}
        {isRequester && ASSIGNED.includes(errand.status) ? (
          <TrackingMap
            drop={{ lat: Number(errand.drop_lat), lng: Number(errand.drop_lng) }}
            runner={
              runnerPos ??
              (errand.runner_lat != null && errand.runner_lng != null
                ? { lat: Number(errand.runner_lat), lng: Number(errand.runner_lng) }
                : null)
            }
          />
        ) : null}

        {/* Who's running it, and where they are. Requester-only — a runner
            doesn't need a card introducing them to themselves, and the live
            position is the customer's tracking view. */}
        {isRequester && errand.runner ? (
          <Card raised style={{ marginTop: space.lg }}>
            <Body style={{ fontFamily: font.bold, marginBottom: space.md }}>Your runner</Body>
            <Row gap={space.md}>
              <View style={s.runnerAvatar}>
                <Text style={{ fontSize: 20 }}>🛵</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Row gap={space.sm}>
                  <Body style={{ fontFamily: font.bold }}>{errand.runner.display_name}</Body>
                  <ConnectionBadge connection={errand.connection} />
                </Row>
                <Caption>
                  ★ {errand.runner.reputation_score.toFixed(2)} · {errand.runner.trips_completed}{" "}
                  trips
                </Caption>
              </View>
              {errand.runner.phone ? (
                <Pill
                  label={errand.runner.phone}
                  bg={colors.greenBg}
                  color={colors.greenText}
                />
              ) : null}
            </Row>

            {errand.connection ? (
              <View style={{ marginTop: space.md }}>
                <ConnectionLine connection={errand.connection} />
              </View>
            ) : null}

            {runnerPos ? (
              <View style={s.livePos}>
                <Caption style={{ color: colors.greenText }}>
                  ● Live · {runnerPos.lat.toFixed(5)}, {runnerPos.lng.toFixed(5)}
                </Caption>
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
          <Card raised style={{ marginTop: space.lg }}>
            <Row justify="space-between">
              <Body style={{ fontFamily: font.bold }}>Order</Body>
              <Body style={{ fontFamily: font.bold, color: colors.brand }}>
                {rupees(errand.items_total)}
              </Body>
            </Row>
            <View style={{ marginTop: space.md, gap: space.md }}>
              {errand.items.map((item) => (
                <Row key={item.id} justify="space-between" gap={space.md}>
                  <View style={{ flex: 1 }}>
                    <Body
                      style={{
                        textDecorationLine: item.is_available ? "none" : "line-through",
                        color: item.is_available ? colors.ink : colors.muted,
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
                          color: item.is_available ? colors.redText : colors.greenText,
                          fontFamily: font.bold,
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

        {/* The money, from whichever side you're on. Relevant from the
            moment a runner is assigned, and still worth seeing afterwards. */}
        {(isRequester || isRunner) && errand.runner_id ? (
          <PaymentSummary errand={errand} isRequester={isRequester} />
        ) : null}

        {/* Handoff secret — runner only */}
        {isRunner && errand.has_handoff_secret && ASSIGNED.includes(errand.status) ? (
          <Card raised style={{ marginTop: space.lg, backgroundColor: colors.brandSoft }}>
            <Body style={{ fontFamily: font.bold }}>🔐 Handoff details</Body>
            {secret ? (
              <View style={{ marginTop: space.md, gap: space.xs }}>
                {secret.otp ? <Text style={s.secretCode}>{secret.otp}</Text> : null}
                {secret.external_ref ? <Caption>Order ref: {secret.external_ref}</Caption> : null}
                {secret.collect_amount > 0 ? (
                  <Caption style={{ color: colors.amberText }}>
                    Pay {rupees(secret.collect_amount)} at pickup — reimbursed on completion.
                  </Caption>
                ) : null}
              </View>
            ) : (
              <>
                <Caption style={{ marginTop: space.xs, marginBottom: space.md }}>
                  Viewing is recorded on the errand's audit trail.
                </Caption>
                <Button title="Reveal code" variant="outline" onPress={revealSecret} />
              </>
            )}
          </Card>
        ) : null}

        {/* What the runner paid. Only for shopping-style errands with a list:
            a fixed-menu vendor order already carries known prices. */}
        {isRunner && errand.status === "ACCEPTED" && errand.items.length > 0 &&
         errand.vendor_id == null ? (
          <PriceClaimSheet errand={errand} onSubmitted={invalidate} />
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
                variant="outline"
                loading={release.isPending}
                onPress={() => release.mutate()}
              />
            </>
          ) : null}

          {isRunner && errand.status === "IN_PROGRESS" ? (
            <Button
              title="Mark delivered"
              size="lg"
              loading={deliver.isPending}
              onPress={() => deliver.mutate()}
            />
          ) : null}

          {isRequester && errand.status === "DELIVERED" ? (
            <Button
              title="Confirm handoff ✓"
              size="lg"
              variant="success"
              loading={complete.isPending}
              onPress={() => complete.mutate()}
            />
          ) : null}

          {isRequester && ["OPEN", "ACCEPTED"].includes(errand.status) ? (
            <Button
              title="Cancel errand"
              variant="ghost"
              loading={cancel.isPending}
              onPress={() =>
                confirm("Cancel this errand?", "The runner will be told it's off.", {
                  confirmLabel: "Cancel errand",
                  cancelLabel: "Keep it",
                  destructive: true,
                }).then((ok) => {
                  if (ok) cancel.mutate(undefined);
                })
              }
            />
          ) : null}
        </View>

        {/* Rating */}
        {isRequester && errand.status === "COMPLETED" && !errand.rated ? (
          <Card raised style={{ marginTop: space.xl, alignItems: "center" }}>
            <Text style={{ fontSize: 32 }}>🎉</Text>
            <Body style={{ fontFamily: font.black, fontSize: font.h3, marginTop: space.xs }}>
              Delivered! Rate your runner
            </Body>
            <Row gap={space.xs} style={{ marginVertical: space.lg }}>
              {[1, 2, 3, 4, 5].map((n) => (
                <Pressable key={n} onPress={() => setStars(n)} hitSlop={6}>
                  <Text style={{ fontSize: 32, color: colors.brand }}>
                    {n <= stars ? "★" : "☆"}
                  </Text>
                </Pressable>
              ))}
            </Row>
            <Button
              title="Submit"
              disabled={stars === 0}
              loading={rate.isPending}
              onPress={() => rate.mutate(stars)}
            />
          </Card>
        ) : null}

        {/* Chat */}
        {errand.runner_id && (isRequester || isRunner) ? <ChatPanel errandId={errand.id} /> : null}

        {/* Audit trail */}
        {events && events.length > 0 ? (
          <>
            <Heading style={{ marginTop: space.xxl, marginBottom: space.md }}>History</Heading>
            <Card raised style={{ gap: space.sm }}>
              {events.map((e) => (
                <Row key={e.id} justify="space-between" gap={space.md}>
                  <Caption style={{ color: colors.ink, flex: 1 }}>
                    {e.event_type.replaceAll("_", " ").toLowerCase()}
                  </Caption>
                  <Caption>{timeAgo(e.created_at)}</Caption>
                </Row>
              ))}
            </Card>
          </>
        ) : null}
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  backBtn: {
    width: 42,
    height: 42,
    borderRadius: radius.pill,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: space.lg,
  },
  backGlyph: { color: colors.brandDark, fontSize: 19, fontFamily: font.bold },

  reward: { color: colors.white, fontSize: 26, fontFamily: font.black },
  rewardLabel: { color: "rgba(255,255,255,0.9)", fontSize: font.small, fontFamily: font.medium },

  node: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: colors.line,
    backgroundColor: colors.white,
    alignItems: "center",
    justifyContent: "center",
  },
  tick: { color: colors.white, fontSize: 11, fontFamily: font.black },
  rail: { width: 2, flex: 1, minHeight: 24, backgroundColor: colors.line, marginVertical: 2 },

  runnerAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  livePos: {
    marginTop: space.md,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: colors.line,
  },

  stockBtn: {
    paddingHorizontal: space.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
  },

  secretCode: { color: colors.ink, fontSize: 28, fontFamily: font.black, letterSpacing: 7 },
});
