import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import Svg, { Circle } from "react-native-svg";

import { colors, font, space } from "../theme";
import { Body, Caption } from "./ui";

/**
 * Circular countdown that unwinds over the poster's wait window, ported from
 * the web tracking page. The server still owns expiry — this only visualises
 * `expires_at`, so a drifting phone clock can't change the outcome.
 */
export function CountdownRing({
  createdAt,
  expiresAt,
  size = 176,
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

  const stroke = 12;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;

  return (
    <View style={{ width: size, height: size, alignSelf: "center" }}>
      {/* -90° so the arc starts at twelve o'clock rather than three. */}
      <Svg width={size} height={size} style={{ transform: [{ rotate: "-90deg" }] }}>
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          stroke={colors.brandSoft}
        />
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          stroke={colors.brand}
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - fraction)}
        />
      </Svg>

      <View style={StyleSheet.absoluteFill}>
        <View style={s.center}>
          {outOfTime ? (
            <Text style={{ fontSize: 38 }}>🛵</Text>
          ) : (
            <>
              <Text style={s.time}>
                {mm}:{String(ss).padStart(2, "0")}
              </Text>
              <Text style={s.label}>until it expires</Text>
            </>
          )}
        </View>
      </View>
    </View>
  );
}

/** The whole "we're finding you a runner" block, ring included. */
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
      <Body style={s.heading}>
        {outOfTime ? "Still searching…" : "Finding a runner nearby"}
      </Body>
      <Caption style={{ textAlign: "center", marginTop: space.xs }}>
        {outOfTime
          ? "No one has accepted yet — one last widen of the search before it expires."
          : "We're offering your errand to verified students heading your way."}
      </Caption>
    </View>
  );
}

const s = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  time: {
    color: colors.brandDark,
    fontSize: 34,
    fontFamily: font.black,
    fontVariant: ["tabular-nums"],
  },
  label: {
    color: colors.muted,
    fontSize: 9,
    fontFamily: font.semi,
    letterSpacing: 1.4,
    textTransform: "uppercase",
    marginTop: 2,
  },
  box: {
    marginTop: space.xl,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: "rgba(255,244,234,0.5)",
    paddingVertical: space.xxl,
    paddingHorizontal: space.xl,
    alignItems: "center",
  },
  heading: {
    fontFamily: font.black,
    fontSize: font.h2,
    marginTop: space.xl,
    textAlign: "center",
  },
});
