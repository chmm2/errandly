/**
 * The Errandly icon set.
 *
 * Every glyph is transcribed from the design canvas's SVG symbols, so the path
 * data here should match that document character for character. All of them sit
 * on a 24px grid at 1.75 stroke unless the design deliberately thickens them,
 * which it does only for the few glyphs made of bare strokes (check, plus,
 * chevron and friends) that would otherwise read lighter than the rest.
 *
 * There are no emoji anywhere in the app. If you need a new glyph, draw it on
 * the same grid rather than reaching for a font.
 */
import Svg, { Circle, Path, Rect } from "react-native-svg";

import { colors } from "../theme";

export type IconName =
  | "order"
  | "run"
  | "wallet"
  | "connects"
  | "profile"
  | "bell"
  | "bowl"
  | "bag"
  | "parcel"
  | "gate"
  | "pin"
  | "lock"
  | "clock"
  | "check"
  | "plus"
  | "minus"
  | "back"
  | "close"
  | "search"
  | "star"
  | "chev"
  | "route"
  | "receipt"
  | "shield"
  | "bike"
  | "in"
  | "out"
  | "scale"
  | "mail"
  | "alert"
  | "camera"
  | "logout"
  | "nav"
  | "cash"
  | "moon"
  | "bolt";

/** Stroke weight per glyph. Anything absent uses the 1.75 house weight. */
const WEIGHT: Partial<Record<IconName, number>> = {
  check: 1.9,
  plus: 1.9,
  minus: 1.9,
  back: 1.8,
  close: 1.8,
  chev: 1.8,
  in: 1.8,
  out: 1.8,
  star: 1.6,
};

export function Icon({
  name,
  size = 24,
  color = colors.brand,
  filled = false,
}: {
  name: IconName;
  size?: number;
  color?: string;
  /** Fill closed shapes too, as a chosen star in a rating row. */
  filled?: boolean;
}) {
  const sw = WEIGHT[name] ?? 1.75;
  const p: StrokeProps = {
    stroke: color,
    strokeWidth: sw,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    fill: filled ? color : "none",
  };

  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {glyph(name, p, color)}
    </Svg>
  );
}

type StrokeProps = {
  stroke: string;
  strokeWidth: number;
  strokeLinecap: "round";
  strokeLinejoin: "round";
  fill: string;
};

function glyph(name: IconName, p: StrokeProps, color: string) {
  switch (name) {
    case "order":
      return (
        <>
          <Circle cx={12} cy={8.4} r={3.4} {...p} />
          <Path d="M5.6 20c1.2-3.6 3.5-5.4 6.4-5.4s5.2 1.8 6.4 5.4" {...p} />
        </>
      );
    case "run":
      return (
        <>
          <Circle cx={15.2} cy={5.9} r={2.1} {...p} />
          <Path d="M15.4 9.6 11.9 12.4l2.5 2.5.7 4.6" {...p} />
          <Path d="M11.9 12.4 8.6 11.3" {...p} />
          <Path d="M4.4 8.2h3.4M3.2 12.2h3" {...p} />
        </>
      );
    case "wallet":
      return (
        <>
          <Path d="M4 9.4V8.2A2.2 2.2 0 0 1 6.2 6h9.4a1.8 1.8 0 0 1 1.8 1.8v1.6" {...p} />
          <Rect x={3.4} y={9.2} width={17.2} height={10.6} rx={3.2} {...p} />
          <Circle cx={16.2} cy={14.5} r={1.15} fill={color} />
        </>
      );
    case "connects":
      return (
        <>
          <Circle cx={8.8} cy={8.8} r={3.2} {...p} />
          <Circle cx={16.4} cy={16} r={3.2} {...p} />
          <Path d="M11.2 11.1l2.8 2.5" {...p} />
        </>
      );
    case "profile":
      return (
        <>
          <Circle cx={12} cy={12} r={8.8} {...p} />
          <Circle cx={12} cy={10} r={2.7} {...p} />
          <Path d="M6.7 18.7a6 6 0 0 1 10.6 0" {...p} />
        </>
      );
    case "bell":
      return (
        <>
          <Path d="M6.6 16.4V11a5.4 5.4 0 0 1 10.8 0v5.4" {...p} />
          <Path d="M4.9 16.4h14.2" {...p} />
          <Path d="M10 19.1a2.2 2.2 0 0 0 4 0" {...p} />
        </>
      );
    case "bowl":
      return (
        <>
          <Path d="M4.2 11.6h15.6a7.8 7.8 0 0 1-15.6 0Z" {...p} />
          <Path d="M12 8.4c0-1.6-1.7-1.9-1.7-3.3" {...p} />
          <Path d="M9.2 20.2h5.6" {...p} />
        </>
      );
    case "bag":
      return (
        <>
          <Path d="M5.6 8.6h12.8l-1 11.4H6.6Z" {...p} />
          <Path d="M9.1 8.6V7a2.9 2.9 0 0 1 5.8 0v1.6" {...p} />
        </>
      );
    case "parcel":
      return (
        <>
          <Path d="M12 3.4 19.8 7.5v9L12 20.6 4.2 16.5v-9Z" {...p} />
          <Path d="M4.2 7.5 12 11.6l7.8-4.1" {...p} />
          <Path d="M12 11.6v9" {...p} />
        </>
      );
    case "gate":
      return (
        <>
          <Path d="M4 20V9.6L12 5.2l8 4.4V20" {...p} />
          <Path d="M9 20v-5.4h6V20" {...p} />
        </>
      );
    case "pin":
      return (
        <>
          <Path d="M12 20.8s5.9-5.2 5.9-9.9a5.9 5.9 0 0 0-11.8 0c0 4.7 5.9 9.9 5.9 9.9Z" {...p} />
          <Circle cx={12} cy={10.8} r={2.2} {...p} />
        </>
      );
    case "lock":
      return (
        <>
          <Rect x={5} y={10.4} width={14} height={9.4} rx={3} {...p} />
          <Path d="M8.6 10.4V8a3.4 3.4 0 0 1 6.8 0v2.4" {...p} />
        </>
      );
    case "clock":
      return (
        <>
          <Circle cx={12} cy={12} r={8.2} {...p} />
          <Path d="M12 7.6V12l3.2 2" {...p} />
        </>
      );
    case "check":
      return <Path d="M5 12.6l4.4 4.2L19 7.4" {...p} />;
    case "plus":
      return <Path d="M12 5.6v12.8M5.6 12h12.8" {...p} />;
    case "minus":
      return <Path d="M5.6 12h12.8" {...p} />;
    case "back":
      return (
        <>
          <Path d="M10.8 5.6 4.6 12l6.2 6.4" {...p} />
          <Path d="M4.6 12H19" {...p} />
        </>
      );
    case "close":
      return <Path d="M6.8 6.8l10.4 10.4M17.2 6.8 6.8 17.2" {...p} />;
    case "search":
      return (
        <>
          <Circle cx={11} cy={11} r={6.2} {...p} />
          <Path d="M15.6 15.6 20 20" {...p} />
        </>
      );
    case "star":
      return (
        <Path
          d="M12 4.6l2.4 4.9 5.4.8-3.9 3.8.9 5.3-4.8-2.5-4.8 2.5.9-5.3-3.9-3.8 5.4-.8Z"
          {...p}
        />
      );
    case "chev":
      return <Path d="M9.6 6.4 16 12l-6.4 5.6" {...p} />;
    case "route":
      return (
        <>
          <Path d="M5.6 19.4c0-5.4 12.8-3.2 12.8-8.6a4.4 4.4 0 0 0-8.8 0" {...p} />
          <Circle cx={5.6} cy={19.4} r={1.7} {...p} />
        </>
      );
    case "receipt":
      return (
        <>
          <Path d="M6.2 4.4h11.6v15.2l-2.9-1.8-2.9 1.8-2.9-1.8-2.9 1.8Z" {...p} />
          <Path d="M9.2 9h5.6M9.2 12.4h3.8" {...p} />
        </>
      );
    case "shield":
      return (
        <>
          <Path d="M12 3.5 19 6v6.1c0 4.2-3 7-7 8.4-4-1.4-7-4.2-7-8.4V6Z" {...p} />
          <Path d="M9.2 12.1l2.2 2.2 4.2-4.4" {...p} />
        </>
      );
    case "bike":
      return (
        <>
          <Circle cx={6.4} cy={16.6} r={2.9} {...p} />
          <Circle cx={17.6} cy={16.6} r={2.9} {...p} />
          <Path d="M6.4 16.6 10 9h4l2.6 7.6" {...p} />
          <Path d="M13 9h3.6" {...p} />
        </>
      );
    case "in":
      return (
        <>
          <Path d="M16.4 7.6 7.6 16.4" {...p} />
          <Path d="M14.6 16.4H7.6V9.4" {...p} />
        </>
      );
    case "out":
      return (
        <>
          <Path d="M7.6 16.4 16.4 7.6" {...p} />
          <Path d="M9.4 7.6h7v7" {...p} />
        </>
      );
    case "scale":
      return (
        <>
          <Path d="M12 5.2v14" {...p} />
          <Path d="M6 9.2h12" {...p} />
          <Path d="M6 9.2 3.8 14.4h4.4Z" {...p} />
          <Path d="M18 9.2l-2.2 5.2h4.4Z" {...p} />
        </>
      );
    case "mail":
      return (
        <>
          <Rect x={3.4} y={6} width={17.2} height={12} rx={3} {...p} />
          <Path d="M4.6 8.2 12 13.6l7.4-5.4" {...p} />
        </>
      );
    case "alert":
      return (
        <>
          <Circle cx={12} cy={12} r={8.4} {...p} />
          <Path d="M12 7.8v5.2" {...p} />
          <Circle cx={12} cy={16.4} r={1} fill={color} />
        </>
      );
    case "camera":
      return (
        <>
          <Rect x={3.4} y={7.4} width={17.2} height={12} rx={3} {...p} />
          <Circle cx={12} cy={13.4} r={3.2} {...p} />
          <Path d="M9 7.4l1.2-2h3.6l1.2 2" {...p} />
        </>
      );
    case "logout":
      return (
        <>
          <Path d="M13.6 5.6H7.4a2 2 0 0 0-2 2v8.8a2 2 0 0 0 2 2h6.2" {...p} />
          <Path d="M11 12h8" {...p} />
          <Path d="M16.4 8.6 19.8 12l-3.4 3.4" {...p} />
        </>
      );
    case "nav":
      return (
        <>
          <Circle cx={12} cy={12} r={8.4} {...p} />
          <Path d="M15.4 8.6l-2 4.4-4.4 2 2-4.4Z" {...p} />
        </>
      );
    case "cash":
      return (
        <>
          <Rect x={3.4} y={7} width={17.2} height={10} rx={2.6} {...p} />
          <Circle cx={12} cy={12} r={2.6} {...p} />
        </>
      );
    case "moon":
      return <Path d="M19 14.6A7.6 7.6 0 0 1 9.4 5a7.8 7.8 0 1 0 9.6 9.6Z" {...p} />;
    case "bolt":
      return <Path d="M13.4 3.4 6.6 13.4h4.2l-1.2 7.2 7-10.2h-4.2Z" {...p} />;
  }
}

/**
 * The wordmark: one unbroken stroke where the crossbar is the route out and the
 * bowl is the loop back. Drawn on the same 64 grid as the app icon so the two
 * never drift apart.
 */
export const MARK_PATH = "M18 33.5 H46 A14 14 0 1 0 41.4 44.6";

export function Mark({
  size = 64,
  color = colors.white,
  weight = 5,
}: {
  size?: number;
  color?: string;
  weight?: number;
}) {
  return (
    <Svg width={size} height={size} viewBox="0 0 64 64">
      <Path d={MARK_PATH} fill="none" stroke={color} strokeWidth={weight} strokeLinecap="round" />
    </Svg>
  );
}

/** The mark inside its rounded brand tile, as it appears in the header lockup. */
export function MarkTile({ size = 46 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 64 64">
      <Rect width={64} height={64} rx={18} fill={colors.brand} />
      <Path
        d={MARK_PATH}
        fill="none"
        stroke={colors.white}
        strokeWidth={5}
        strokeLinecap="round"
      />
    </Svg>
  );
}
