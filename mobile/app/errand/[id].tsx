import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import {
  cancelErrand,
  completeErrand,
  deliverErrand,
  type Errand,
  type ErrandEvent,
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
import { ConnectionBadge, ConnectionLine } from "../../src/components/ConnectionBadge";
import { FindingRunner } from "../../src/components/CountdownRing";
import { Icon } from "../../src/components/icons";
import { OverspendNotice } from "../../src/components/OverspendNotice";
import { PaymentSummary } from "../../src/components/PaymentSummary";
import { PriceClaimSheet } from "../../src/components/PriceClaimSheet";
import { TrackingMap } from "../../src/components/TrackingMap";
import {
  Avatar,
  Button,
  EmptyState,
  Heading,
  Hero,
  IconTile,
  Pill,
  PulseRing,
  Screen,
  SkeletonRow,
} from "../../src/components/ui";
import { apiErrorMessage } from "../../src/lib/api";
import { confirm, notify } from "../../src/lib/dialog";
import { goBack } from "../../src/lib/nav";
import { useSocket } from "../../src/lib/ws";
import { useAuth } from "../../src/stores/auth";
import {
  categoryIcon,
  colors,
  ETA_MINUTES,
  font,
  onBrand,
  radius,
  rupees,
  shadow,
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

/** Runner is assigned and moving: show their card and position. */
const ASSIGNED: Errand["status"][] = ["ACCEPTED", "IN_PROGRESS", "DELIVERED"];

/** The happy path, in order. Drives the stepper on the live status card. */
const STEPS: { status: Errand["status"]; label: string; headline: string }[] = [
  { status: "OPEN", label: "Posted", headline: "Waiting for a runner" },
  { status: "ACCEPTED", label: "Assigned", headline: "Runner assigned" },
  { status: "IN_PROGRESS", label: "Picked up", headline: "Picked up" },
  { status: "DELIVERED", label: "Delivered", headline: "Delivered" },
  { status: "COMPLETED", label: "Confirmed", headline: "Confirmed" },
];

function clock(iso: string | null | undefined): string | null {
  if (!iso) return null;
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/**
 * When each step happened. Every timestamp but one lives on the errand row;
 * pickup is only recorded as an event, so it is read from the audit trail.
 */
function stepTimes(errand: Errand, events: ErrandEvent[] | undefined): (string | null)[] {
  const pickedUp = events?.find((e) => e.event_type === "PICKED_UP")?.created_at;
  return [
    clock(errand.created_at),
    clock(errand.accepted_at),
    clock(pickedUp),
    clock(errand.delivered_at),
    clock(errand.completed_at),
  ];
}

/** Minutes until the rough ETA, ticking so the number stays honest. */
function useEtaMinutes(acceptedAt: string | null, active: boolean): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 20_000);
    return () => clearInterval(t);
  }, [active]);
  if (!active || !acceptedAt) return null;
  const left = Math.round((new Date(acceptedAt).getTime() + ETA_MINUTES * 60_000 - now) / 60_000);
  return Math.max(1, left);
}

/**
 * The teal card that says where the errand has got to: the current step in
 * words, an ETA while someone is moving, and a five-node stepper underneath
 * with the time each step landed.
 */
function LiveStatus({ errand, events }: { errand: Errand; events: ErrandEvent[] | undefined }) {
  const index = Math.max(0, STEPS.findIndex((st) => st.status === errand.status));
  const moving = errand.status === "ACCEPTED" || errand.status === "IN_PROGRESS";
  const eta = useEtaMinutes(errand.accepted_at, moving);
  const times = stepTimes(errand, events);
  const finished = errand.status === "COMPLETED";

  return (
    <View style={[s.live, shadow.raised]}>
      <View style={s.liveTop}>
        <View style={s.liveDisc} pointerEvents="none" />
        <View style={s.liveRow}>
          <View style={s.liveTile}>
            <Icon name={finished ? "check" : "bike"} size={26} color={colors.white} />
            {!finished ? (
              <PulseRing color="rgba(227,178,119,0.7)" width={1.5} round={false} />
            ) : null}
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <View style={s.liveEyebrowRow}>
              <View style={s.liveDot} />
              <Text style={s.liveEyebrow}>
                Step {index + 1} of {STEPS.length}
              </Text>
            </View>
            <Text style={s.liveHeadline}>{STEPS[index].headline}</Text>
          </View>
          {eta != null ? (
            <View style={{ alignItems: "flex-end" }}>
              <Text style={s.eta}>{eta}</Text>
              <Text style={s.etaLabel}>min away</Text>
            </View>
          ) : null}
        </View>
      </View>

      <View style={s.stepper}>
        <View style={s.track}>
          <View style={s.trackBase} />
          <View
            style={[s.trackFill, { width: `${(index / (STEPS.length - 1)) * 100}%` }]}
          />
          <View style={s.nodes}>
            {STEPS.map((st, i) => {
              const done = i < index || finished;
              const current = i === index && !finished;
              if (done) {
                return (
                  <View key={st.status} style={s.nodeDone}>
                    <Icon name="check" size={13} color={colors.brandDeep} />
                  </View>
                );
              }
              if (current) {
                return (
                  <View key={st.status} style={s.nodeCurrent}>
                    <PulseRing
                      color="rgba(227,178,119,0.8)"
                      style={{ top: -5, left: -5, right: -5, bottom: -5 }}
                      duration={2400}
                    />
                  </View>
                );
              }
              return <View key={st.status} style={s.nodeTodo} />;
            })}
          </View>
        </View>

        <View style={s.labels}>
          {STEPS.map((st, i) => {
            const reached = i <= index;
            const current = i === index && !finished;
            return (
              <View key={st.status} style={s.labelCol}>
                <Text
                  style={[
                    s.stepLabel,
                    !reached && { color: "rgba(255,255,255,0.42)" },
                    current && { color: colors.moneyLight, fontFamily: font.black },
                  ]}
                >
                  {st.label}
                </Text>
                {reached && times[i] ? (
                  <Text style={[s.stepTime, current && { color: colors.moneyLight }]}>
                    {times[i]}
                  </Text>
                ) : null}
              </View>
            );
          })}
        </View>
      </View>
    </View>
  );
}

export default function ErrandDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const myId = useAuth((s) => s.user?.id);
  const insets = useSafeAreaInsets();

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

  /**
   * Leave the errand behind after an action that ends your stake in it.
   *
   * Cancelling and handing back both used to just refetch, so you stayed on a
   * detail screen for an errand that was over or no longer yours: every button
   * gone, a status you can't act on, and the back gesture returning you to it.
   * Popping the screen also drops it from the stack, so it can't be swiped
   * back into.
   *
   * The wallet is invalidated too: cancelling releases the escrow hold, so the
   * balance behind this screen is stale the moment the cancel succeeds.
   */
  const leaveErrand = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["my-errands"] });
    queryClient.invalidateQueries({ queryKey: ["runner-feed"] });
    queryClient.invalidateQueries({ queryKey: ["wallet"] });
    goBack(router);
  }, [queryClient, router]);

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
    onSuccess: leaveErrand,
    onError: (err) => notify("Couldn't release", apiErrorMessage(err)),
  });
  const cancel = useMutation({
    mutationFn: (reason?: string) => cancelErrand(id!, reason),
    onSuccess: leaveErrand,
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
  // `isLoading || !errand`, so any error (an expired token, a dropped
  // connection, a 404) left the spinner up forever with nothing to act on.
  if (isError || (!isLoading && !errand)) {
    return (
      <Screen padded={false} edges={[]} tabBarClearance={false}>
        <Hero compact onBack={() => goBack(router)} title="Errand" />
        <View style={{ padding: 22 }}>
          <EmptyState
            icon="alert"
            title="Couldn't load this errand"
            body={error ? apiErrorMessage(error) : "It may have been removed, or the link is wrong."}
            action={<Button title="Try again" onPress={() => refetch()} />}
          />
        </View>
      </Screen>
    );
  }

  if (isLoading || !errand) {
    return (
      <Screen padded={false} edges={[]} tabBarClearance={false}>
        <Hero compact onBack={() => goBack(router)} title="Loading errand…" />
        <View style={{ padding: 22, gap: space.sm }}>
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </View>
      </Screen>
    );
  }

  const isRequester = errand.requester_id === myId;
  const isRunner = errand.runner_id === myId;
  const status = statusStyle[errand.status];
  const terminal = ["CANCELLED", "EXPIRED"].includes(errand.status);
  const party = isRequester || isRunner;

  async function revealSecret() {
    try {
      setSecret(await fetchHandoffSecret(id!));
    } catch (err) {
      notify("Couldn't reveal code", apiErrorMessage(err));
    }
  }

  function askCancel() {
    const who = errand?.runner?.display_name;
    confirm(
      "Cancel this errand?",
      who
        ? `${who} is on it. They will be told, and your hold is released.`
        : "It comes off the queue and your hold is released.",
      {
        confirmLabel: "Cancel errand",
        cancelLabel: "Keep it",
        destructive: true,
      },
    ).then((ok) => {
      if (ok) cancel.mutate(undefined);
    });
  }

  // The footer carries whichever single step is next for you. Everything else
  // lives in the scrolling body, so the button you need is always in reach.
  const footer = (() => {
    if (isRunner && errand.status === "ACCEPTED") {
      return (
        <>
          {/* Gated on the server's own flag rather than on anything decided
              here: the endpoint refuses the same case, and a button that
              disagreed with it would fail when pressed. */}
          <Button
            title="Mark picked up"
            size="lg"
            icon="bag"
            loading={pickup.isPending}
            disabled={errand.price_report_pending === true}
            onPress={() => pickup.mutate()}
          />
          {errand.price_report_pending ? (
            <Text style={s.footHint}>
              Report what you paid above first. That is what you get reimbursed for.
            </Text>
          ) : null}
          <Pressable
            onPress={() => release.mutate()}
            disabled={release.isPending}
            hitSlop={8}
            style={s.footLink}
          >
            <Text style={[s.footLinkText, { color: colors.muted }]}>
              {release.isPending ? "Handing back…" : "Hand back to queue"}
            </Text>
          </Pressable>
        </>
      );
    }
    if (isRunner && errand.status === "IN_PROGRESS") {
      return (
        <Button
          title="Mark delivered"
          size="lg"
          icon="check"
          loading={deliver.isPending}
          onPress={() => deliver.mutate()}
        />
      );
    }
    if (isRequester && errand.status === "DELIVERED") {
      return (
        <Button
          title="Confirm handoff"
          size="lg"
          icon="check"
          loading={complete.isPending}
          onPress={() => complete.mutate()}
        />
      );
    }
    if (isRequester && ["OPEN", "ACCEPTED"].includes(errand.status)) {
      return (
        <Pressable
          onPress={askCancel}
          disabled={cancel.isPending}
          hitSlop={8}
          style={s.footLink}
          accessibilityRole="button"
        >
          <Text style={s.footLinkText}>
            {cancel.isPending ? "Cancelling…" : "Cancel errand"}
          </Text>
        </Pressable>
      );
    }
    return null;
  })();

  const runnerAt =
    runnerPos ??
    (errand.runner_lat != null && errand.runner_lng != null
      ? { lat: Number(errand.runner_lat), lng: Number(errand.runner_lng) }
      : null);

  return (
    <View style={s.root}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingBottom: footer ? 150 : 40 }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <Hero
          compact
          onBack={() => goBack(router)}
          topRight={
            <Pill
              label={status.label}
              icon={terminal ? "close" : "bike"}
              bg={onBrand.fill}
              color={colors.white}
            />
          }
          title={errand.title}
          titleStyle={s.heroTitle}
        >
          <View style={s.rewardRow}>
            <Text style={s.reward}>{rupees(errand.reward)}</Text>
            <Text style={s.rewardLabel}>
              reward
              {errand.collect_amount > 0
                ? `, plus ${rupees(errand.collect_amount)} reimbursed`
                : ""}
            </Text>
          </View>
        </Hero>

        <View style={s.body}>
          {/* What it is and where it goes. */}
          <View style={s.card}>
            <View style={s.whatRow}>
              <IconTile icon={categoryIcon[errand.category] ?? "gate"} size={44} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.route} numberOfLines={2}>
                  {errand.pickup_label}
                  {errand.drop_label ? ` to ${errand.drop_label}` : ""}
                </Text>
                {errand.notes ? (
                  <Text style={s.notes} numberOfLines={3}>
                    “{errand.notes}”
                  </Text>
                ) : null}
              </View>
            </View>
          </View>

          {/* The other direction: a runner looking at someone else's errand
              sees how they connect to whoever posted it. This is the deciding
              fact when choosing which run to take, so it sits above the fold
              rather than in the payment block at the bottom. */}
          {!isRequester && errand.connection ? (
            <View style={s.card}>
              <ConnectionLine connection={errand.connection} />
            </View>
          ) : null}

          {/* Waiting for a runner. Requester only: this is *their* deadline
              ticking down. A runner browsing the same errand has no stake in
              it and shouldn't be shown the poster's private countdown. */}
          {isRequester && errand.status === "OPEN" && errand.expires_at ? (
            <FindingRunner createdAt={errand.created_at} expiresAt={errand.expires_at} />
          ) : null}

          {/* Live map: the requester's tracking view, only while someone is
              actually on the way. */}
          {isRequester && ASSIGNED.includes(errand.status) ? (
            <TrackingMap
              drop={{ lat: Number(errand.drop_lat), lng: Number(errand.drop_lng) }}
              runner={runnerAt}
            />
          ) : null}

          {/* Who's running it. Requester only: a runner doesn't need a card
              introducing them to themselves. */}
          {isRequester && errand.runner ? (
            <View style={s.card}>
              <View style={s.runnerRow}>
                <Avatar name={errand.runner.display_name} size={46} />
                <View style={{ flex: 1, minWidth: 0 }}>
                  <View style={s.runnerNameRow}>
                    <Text numberOfLines={1} style={s.runnerName}>
                      {errand.runner.display_name}
                    </Text>
                    <ConnectionBadge connection={errand.connection} />
                  </View>
                  <Text style={s.runnerMeta}>
                    {errand.runner.reputation_score.toFixed(2)} rating,{" "}
                    {errand.runner.trips_completed} trip
                    {errand.runner.trips_completed === 1 ? "" : "s"}
                  </Text>
                  {errand.runner.phone ? (
                    <Text style={s.runnerPhone}>{errand.runner.phone}</Text>
                  ) : null}
                </View>
                <View style={s.routeDisc}>
                  <Icon name="route" size={19} color={colors.credit} />
                </View>
              </View>
              {errand.connection && errand.connection.degree !== 1 ? (
                <View style={{ marginTop: space.md }}>
                  <ConnectionLine connection={errand.connection} />
                </View>
              ) : null}
            </View>
          ) : null}

          {/* Where it has got to. Both parties, nobody else: a runner browsing
              open work is deciding whether to take it, and where somebody
              else's errand has got to is not part of that decision. The
              backend refuses non-parties a non-open errand outright, so this
              is the second lock rather than the only one. */}
          {party && !terminal && errand.status !== "OPEN" ? (
            <LiveStatus errand={errand} events={events} />
          ) : null}

          {/* Order items */}
          {errand.items.length > 0 ? (
            <View style={s.card}>
              <View style={s.cardHead}>
                <Icon name="bag" size={17} color={colors.brand} />
                <Text style={s.cardTitle}>Order</Text>
                <Text style={s.cardValue}>{rupees(errand.items_total)}</Text>
              </View>
              <View style={{ gap: 10, marginTop: 10 }}>
                {errand.items.map((item) => (
                  <View key={item.id} style={s.itemRow}>
                    <View style={{ flex: 1 }}>
                      <Text
                        style={[
                          s.itemName,
                          !item.is_available && {
                            textDecorationLine: "line-through",
                            color: colors.muted,
                          },
                        ]}
                      >
                        {item.quantity}× {item.name_snapshot}
                      </Text>
                      {item.note ? <Text style={s.itemNote}>{item.note}</Text> : null}
                    </View>

                    {isRunner && ["ACCEPTED", "IN_PROGRESS"].includes(errand.status) ? (
                      <Pressable
                        onPress={() =>
                          toggleItem.mutate({ itemId: item.id, available: !item.is_available })
                        }
                        style={s.stockBtn}
                      >
                        <Text
                          style={[
                            s.stockText,
                            { color: item.is_available ? colors.caution : colors.credit },
                          ]}
                        >
                          {item.is_available ? "Out of stock" : "Restore"}
                        </Text>
                      </Pressable>
                    ) : item.unit_price_snapshot != null ? (
                      <Text style={s.itemPrice}>
                        {rupees(item.unit_price_snapshot * item.quantity)}
                      </Text>
                    ) : null}
                  </View>
                ))}
              </View>
            </View>
          ) : null}

          {/* The money, from whichever side you're on. Relevant from the
              moment a runner is assigned, and still worth seeing afterwards. */}
          {party && errand.runner_id ? (
            <PaymentSummary errand={errand} isRequester={isRequester} />
          ) : null}

          {/* Handoff secret, runner only */}
          {isRunner && errand.has_handoff_secret && ASSIGNED.includes(errand.status) ? (
            <View style={[s.card, { backgroundColor: colors.brandWash, borderColor: colors.lineStrong }]}>
              <View style={s.cardHead}>
                <Icon name="lock" size={17} color={colors.brand} />
                <Text style={s.cardTitle}>Handoff details</Text>
              </View>
              {secret ? (
                <View style={{ marginTop: space.md, gap: space.xs }}>
                  {secret.otp ? <Text style={s.secretCode}>{secret.otp}</Text> : null}
                  {secret.external_ref ? (
                    <Text style={s.itemNote}>Order ref: {secret.external_ref}</Text>
                  ) : null}
                  {secret.collect_amount > 0 ? (
                    <Text style={[s.itemNote, { color: colors.warnText }]}>
                      Pay {rupees(secret.collect_amount)} at pickup, reimbursed on completion.
                    </Text>
                  ) : null}
                </View>
              ) : (
                <>
                  <Text style={[s.itemNote, { marginTop: space.xs, marginBottom: space.md }]}>
                    Viewing is recorded on the errand's audit trail.
                  </Text>
                  <Button title="Reveal code" variant="outline" icon="lock" onPress={revealSecret} />
                </>
              )}
            </View>
          ) : null}

          {/* What the runner paid. Only for shopping-style errands with a
              list: a fixed-menu vendor order already carries known prices. */}
          {isRunner &&
          errand.status === "ACCEPTED" &&
          errand.items.length > 0 &&
          errand.vendor_id == null ? (
            <PriceClaimSheet errand={errand} onSubmitted={invalidate} />
          ) : null}

          {isRequester && errand.status === "DELIVERED" ? (
            <OverspendNotice errand={errand} />
          ) : null}

          {/* Rating */}
          {isRequester && errand.status === "COMPLETED" && !errand.rated ? (
            <View style={[s.card, { alignItems: "center", paddingVertical: space.xl }]}>
              <View style={s.rateIcon}>
                <Icon name="check" size={26} color={colors.credit} />
              </View>
              <Text style={s.rateTitle}>Delivered. Rate your runner</Text>
              <View style={s.stars}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <Pressable
                    key={n}
                    onPress={() => setStars(n)}
                    hitSlop={6}
                    accessibilityRole="button"
                    accessibilityLabel={`${n} star${n === 1 ? "" : "s"}`}
                  >
                    <Icon name="star" size={34} color={colors.brand} filled={n <= stars} />
                  </Pressable>
                ))}
              </View>
              <Button
                title="Submit rating"
                disabled={stars === 0}
                loading={rate.isPending}
                onPress={() => rate.mutate(stars)}
              />
            </View>
          ) : null}

          {/* Chat */}
          {errand.runner_id && party ? <ChatPanel errandId={errand.id} /> : null}

          {/* Audit trail */}
          {events && events.length > 0 ? (
            <>
              <Heading style={{ marginTop: space.xl, marginBottom: 10, fontSize: 16 }}>
                History
              </Heading>
              <View style={s.history}>
                {events.map((e, i) => (
                  <View key={e.id} style={[s.historyRow, i > 0 && s.historyDivider]}>
                    <Text style={s.historyText}>
                      {e.event_type.replaceAll("_", " ").toLowerCase()}
                    </Text>
                    <Text style={s.historyTime}>{timeAgo(e.created_at)}</Text>
                  </View>
                ))}
              </View>
            </>
          ) : null}
        </View>
      </ScrollView>

      {footer ? (
        <LinearGradient
          colors={["rgba(247,250,249,0)", colors.bgSoft]}
          locations={[0, 0.45]}
          style={[s.footer, { paddingBottom: Math.max(insets.bottom, 12) + 18 }]}
        >
          {footer}
        </LinearGradient>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bgSoft },

  heroTitle: { fontSize: 23, lineHeight: 29, letterSpacing: -0.7 },
  rewardRow: { flexDirection: "row", alignItems: "baseline", gap: 8, marginTop: 10 },
  reward: { color: colors.white, fontSize: 26, fontFamily: font.black, letterSpacing: -0.7 },
  rewardLabel: { color: onBrand.text, fontSize: 12.5, fontFamily: font.regular },

  body: { paddingHorizontal: 22, paddingTop: 0 },

  card: {
    marginTop: 12,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.card,
    padding: 14,
  },
  cardHead: { flexDirection: "row", alignItems: "center", gap: 9 },
  cardTitle: { flex: 1, color: colors.ink, fontSize: 13, fontFamily: font.bold },
  cardValue: { color: colors.ink, fontSize: 15, fontFamily: font.black },

  whatRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  route: { color: colors.inkSoft, fontSize: 13, fontFamily: font.semi, lineHeight: 19 },
  notes: { color: colors.muted, fontSize: 12, fontFamily: font.regular, marginTop: 3 },

  runnerRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  runnerNameRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  runnerName: { flexShrink: 1, color: colors.ink, fontSize: 14.5, fontFamily: font.bold },
  runnerMeta: { color: colors.muted, fontSize: 11.5, fontFamily: font.regular, marginTop: 2 },
  runnerPhone: { color: colors.mutedCool, fontSize: 11, fontFamily: font.mono, marginTop: 2 },
  routeDisc: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.creditBg,
    alignItems: "center",
    justifyContent: "center",
  },

  live: {
    marginTop: 12,
    borderRadius: radius.big,
    overflow: "hidden",
    backgroundColor: colors.brand,
  },
  liveTop: { paddingHorizontal: 16, paddingTop: 16, paddingBottom: 14, overflow: "hidden" },
  liveDisc: {
    position: "absolute",
    width: 170,
    height: 170,
    borderRadius: 85,
    backgroundColor: "rgba(255,255,255,0.055)",
    top: -80,
    right: -50,
  },
  liveRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  liveTile: {
    width: 52,
    height: 52,
    borderRadius: radius.xl,
    backgroundColor: onBrand.fillSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  liveEyebrowRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  liveDot: { width: 7, height: 7, borderRadius: 3.5, backgroundColor: colors.creditLight },
  liveEyebrow: {
    color: onBrand.textDim,
    fontSize: 10.5,
    fontFamily: font.bold,
    letterSpacing: 1.5,
    textTransform: "uppercase",
  },
  liveHeadline: {
    color: colors.white,
    fontSize: 21,
    fontFamily: font.black,
    letterSpacing: -0.6,
    marginTop: 3,
  },
  eta: { color: colors.moneyLight, fontSize: 22, fontFamily: font.black, letterSpacing: -0.6 },
  etaLabel: { color: "rgba(255,255,255,0.6)", fontSize: 10, fontFamily: font.regular },

  stepper: { backgroundColor: "#1E3D3E", paddingHorizontal: 16, paddingTop: 14, paddingBottom: 15 },
  track: { height: 22, marginHorizontal: 20, justifyContent: "center" },
  trackBase: {
    position: "absolute",
    left: 0,
    right: 0,
    height: 3,
    borderRadius: 2,
    backgroundColor: onBrand.hairline,
  },
  trackFill: {
    position: "absolute",
    left: 0,
    height: 3,
    borderRadius: 2,
    backgroundColor: colors.moneyLight,
  },
  nodes: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginHorizontal: -10,
  },
  nodeDone: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.moneyLight,
    alignItems: "center",
    justifyContent: "center",
  },
  nodeCurrent: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.white,
    borderWidth: 3,
    borderColor: colors.moneyLight,
  },
  nodeTodo: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: "#1E3D3E",
    borderWidth: 2,
    borderColor: "rgba(255,255,255,0.3)",
  },
  labels: { flexDirection: "row", justifyContent: "space-between", marginTop: 10 },
  labelCol: { width: 60, alignItems: "center" },
  stepLabel: {
    color: "rgba(255,255,255,0.85)",
    fontSize: 10.5,
    fontFamily: font.bold,
    textAlign: "center",
  },
  stepTime: {
    color: onBrand.textFaint,
    fontSize: 9.5,
    fontFamily: font.regular,
    marginTop: 1,
  },

  itemRow: { flexDirection: "row", alignItems: "center", gap: space.md },
  itemName: { color: colors.ink, fontSize: 13.5, fontFamily: font.semi },
  itemNote: { color: colors.muted, fontSize: 11.5, fontFamily: font.regular },
  itemPrice: { color: colors.inkSoft, fontSize: 12.5, fontFamily: font.semi },
  stockBtn: {
    paddingHorizontal: space.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
  },
  stockText: { fontSize: 11, fontFamily: font.bold },

  secretCode: { color: colors.ink, fontSize: 26, fontFamily: font.monoMedium, letterSpacing: 7 },

  rateIcon: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: colors.creditBg,
    alignItems: "center",
    justifyContent: "center",
  },
  rateTitle: { color: colors.ink, fontSize: 17, fontFamily: font.black, marginTop: 12 },
  stars: { flexDirection: "row", gap: 6, marginVertical: space.lg },

  history: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.xxl,
    overflow: "hidden",
  },
  historyRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: space.md,
    paddingHorizontal: 15,
    paddingVertical: 11,
  },
  historyDivider: { borderTopWidth: 1, borderTopColor: colors.hairlineSoft },
  historyText: { flex: 1, color: colors.inkSoft, fontSize: 12.5, fontFamily: font.regular },
  historyTime: { color: colors.mutedCool, fontSize: 11.5, fontFamily: font.regular },

  footer: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: 22,
    paddingTop: 22,
    gap: 4,
  },
  footHint: {
    color: colors.muted,
    fontSize: 12,
    fontFamily: font.regular,
    textAlign: "center",
    marginTop: 6,
  },
  footLink: { alignItems: "center", paddingVertical: 12 },
  footLinkText: { color: colors.caution, fontSize: 13, fontFamily: font.bold },
});
