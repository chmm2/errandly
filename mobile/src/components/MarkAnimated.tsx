/**
 * The Errandly mark, drawing itself.
 *
 * Two things happen on one shared clock, exactly as the design canvas states
 * them: the stroke draws on over the first 55 per cent of the cycle and then
 * holds, and a copper dot runs the full path once, fading in and out at the
 * ends so it never pops.
 *
 * The web version gets the dot for free from `offset-path`, which React Native
 * has no equivalent of, so the geometry is solved here instead. The mark is a
 * horizontal line followed by a single elliptical arc, and the arc is converted
 * from SVG's endpoint form to a centre and a sweep using the conversion in the
 * SVG spec (F.6.5). Sampling that gives the dot the same trajectory the browser
 * computes, rather than an eyeballed approximation.
 */
import { useEffect, useRef } from "react";
import { Animated, Easing } from "react-native";
import Svg, { Circle, Path } from "react-native-svg";

import { colors } from "../theme";
import { MARK_PATH } from "./icons";

const AnimatedPath = Animated.createAnimatedComponent(Path);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

/* The mark's two segments, matching MARK_PATH: "M18 33.5 H46 A14 14 0 1 0 41.4 44.6" */
const LINE_FROM = { x: 18, y: 33.5 };
const LINE_TO = { x: 46, y: 33.5 };
const ARC_TO = { x: 41.4, y: 44.6 };
const ARC_R = 14;
const LARGE_ARC: boolean = true;
const SWEEP: boolean = false;

/**
 * SVG endpoint-to-centre arc conversion. Only the zero-rotation circular case
 * is needed here, which drops the rotation terms but is otherwise the spec
 * algorithm verbatim.
 */
function arcCentre() {
  const { x: x1, y: y1 } = LINE_TO;
  const { x: x2, y: y2 } = ARC_TO;
  let rx = ARC_R;
  let ry = ARC_R;

  const dx2 = (x1 - x2) / 2;
  const dy2 = (y1 - y2) / 2;

  // Grow the radii if they are too small to join the endpoints at all.
  const lambda = (dx2 * dx2) / (rx * rx) + (dy2 * dy2) / (ry * ry);
  if (lambda > 1) {
    const k = Math.sqrt(lambda);
    rx *= k;
    ry *= k;
  }

  const num = rx * rx * ry * ry - rx * rx * dy2 * dy2 - ry * ry * dx2 * dx2;
  const den = rx * rx * dy2 * dy2 + ry * ry * dx2 * dx2;
  const coef = (LARGE_ARC !== SWEEP ? 1 : -1) * Math.sqrt(Math.max(0, num / den));

  const cxp = (coef * (rx * dy2)) / ry;
  const cyp = (coef * -(ry * dx2)) / rx;
  const cx = cxp + (x1 + x2) / 2;
  const cy = cyp + (y1 + y2) / 2;

  const theta1 = Math.atan2((dy2 - cyp) / ry, (dx2 - cxp) / rx);
  const theta2 = Math.atan2((-dy2 - cyp) / ry, (-dx2 - cxp) / rx);
  let delta = theta2 - theta1;
  if (!SWEEP && delta > 0) delta -= 2 * Math.PI;
  if (SWEEP && delta < 0) delta += 2 * Math.PI;

  return { cx, cy, rx, ry, theta1, delta };
}

const ARC = arcCentre();
const LINE_LEN = LINE_TO.x - LINE_FROM.x;
const ARC_LEN = Math.abs(ARC.delta) * ARC_R;

/**
 * The measured length, 103.55 units. The design hard-codes a dash of 240, which
 * is a safe over-estimate rather than a measurement: because the dash is longer
 * than the path, the stroke stays completely hidden until the offset falls
 * below the real length, so more than half of the draw window there is dead
 * time and the mark appears to snap in. Measuring gives the same finished
 * drawing with the stroke actually growing across the whole window.
 */
const TOTAL_LEN = LINE_LEN + ARC_LEN;

/** Sample the mark at `t` in [0, 1] of its length. */
function pointAt(t: number): { x: number; y: number } {
  const d = t * TOTAL_LEN;
  if (d <= LINE_LEN) {
    return { x: LINE_FROM.x + d, y: LINE_FROM.y };
  }
  const u = (d - LINE_LEN) / ARC_LEN;
  const angle = ARC.theta1 + u * ARC.delta;
  return { x: ARC.cx + ARC.rx * Math.cos(angle), y: ARC.cy + ARC.ry * Math.sin(angle) };
}

/** Pre-sampled trajectory. 48 steps is past the point where the dot looks stepped. */
const STEPS = 48;
const TRAIL = Array.from({ length: STEPS + 1 }, (_, i) => pointAt(i / STEPS));

export function AnimatedMark({
  size = 76,
  color = "rgba(255,255,255,0.9)",
  dot = colors.moneyLight,
  weight = 5,
  duration = 5000,
}: {
  size?: number;
  color?: string;
  dot?: string;
  weight?: number;
  duration?: number;
}) {
  const t = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.timing(t, {
        toValue: 1,
        duration,
        // The design's cubic-bezier(.6,0,.2,1): quick in the middle, eased at both ends.
        easing: Easing.bezier(0.6, 0, 0.2, 1),
        useNativeDriver: false,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [t, duration]);

  // Draw on over the first 55 per cent, then hold at full.
  const dashOffset = t.interpolate({
    inputRange: [0, 0.55, 1],
    outputRange: [TOTAL_LEN, 0, 0],
  });

  const cx = t.interpolate({
    inputRange: TRAIL.map((_, i) => i / STEPS),
    outputRange: TRAIL.map((pt) => pt.x),
  });
  const cy = t.interpolate({
    inputRange: TRAIL.map((_, i) => i / STEPS),
    outputRange: TRAIL.map((pt) => pt.y),
  });
  const dotOpacity = t.interpolate({
    inputRange: [0, 0.08, 0.92, 1],
    outputRange: [0, 1, 1, 0],
  });

  return (
    <Svg width={size} height={size} viewBox="0 0 64 64">
      <AnimatedPath
        d={MARK_PATH}
        fill="none"
        stroke={color}
        strokeWidth={weight}
        strokeLinecap="round"
        strokeDasharray={TOTAL_LEN}
        strokeDashoffset={dashOffset}
      />
      <AnimatedCircle r={3.2} fill={dot} cx={cx} cy={cy} opacity={dotOpacity} />
    </Svg>
  );
}
