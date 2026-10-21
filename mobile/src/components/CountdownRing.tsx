import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import Svg, { Circle } from "react-native-svg";

import { colors, font, onBrand, radius } from "../theme";
import { Icon } from "./icons";

/**
 * Circular countdown that unwinds over the poster's wait window. The server
 * still owns expiry: this only visualises `expires_at`, so a drifting phone
 * clock can't change the outcome.
 *
 * Drawn for the teal "finding a runner" card, so the track is a translucent
 * white and the remaining time is copper, the colour the design keeps for
 * anything that is counting down on the user's behalf.
 */
export function CountdownRing({
  createdAt,
  expiresAt,
  size = 56,
}: {
  createdAt: string;
  expiresAt: string;
  size?: number;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const start = new Date(createdAt).getTime();
  const end = new Date(expiresAt).getTime();
  const total = Math.max(1, end - start);
  const remaining = Math.max(0, end - now);
  const fraction = Math.max(0, Math.min(1, remaining / total));

  const mm = Math.floor(remaining / 60000);
  const ss = Math.floor((remaining % 60000) / 1000);
  const outOfTime = remaining === 0;

  const stroke = 4;
  const r = (size - stroke * 2) / 2;
  const circ = 2 * Math.PI * r;

  return (
    <View style={{ width: size, height: size }}>
      {/* -90 degrees so the arc starts at twelve o'clock rather than three. */}
      <Svg width={size} height={size} style={{ transform: [{ rotate: "-90deg" }] }}>
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          stroke="rgba(255,255,255,0.2)"
        />
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          stroke={colors.moneyLight}
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - fraction)}
        />
      </Svg>

      <View style={s.center}>
        {outOfTime ? (
          <Icon name="bike" size={22} color={colors.white} />
        ) : (
          <Text style={s.time}>
            {mm}:{String(ss).padStart(2, "0")}
          </Text>
        )}
      </View>
    </View>
  );
}

/** The whole "we're finding you a runner" card, ring included. */
export function FindingRunner({
  createdAt,
  expiresAt,
}: {
  createdAt: string;
  expiresAt: string;
}) {
  const outOfTime = Date.now() >= new Date(expiresAt).getTime();
  return (
    <View style={s.box}>
      <CountdownRing createdAt={createdAt} expiresAt={expiresAt} />
      <View style={{ flex: 1 }}>
        <Text style={s.heading}>{outOfTime ? "Still searching…" : "Finding a runner"}</Text>
        <Text style={s.body}>
          {outOfTime
            ? "No one has accepted yet. One last widening of the search before it expires."
            : "Asking your friends first, then their friends."}
        </Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  center: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: "center",
    justifyContent: "center",
  },
  time: {
    color: colors.white,
    fontSize: 12,
    fontFamily: font.black,
    fontVariant: ["tabular-nums"],
  },
  box: {
    marginTop: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    borderRadius: radius.card,
    backgroundColor: colors.brand,
    padding: 14,
  },
  heading: { color: colors.white, fontSize: 14, fontFamily: font.bold },
  body: {
    color: onBrand.text,
    fontSize: 12,
    fontFamily: font.regular,
    lineHeight: 18,
    marginTop: 2,
  },
});
