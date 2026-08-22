import { useMemo, useRef } from "react";
import { StyleSheet, View } from "react-native";
import { WebView } from "react-native-webview";

import { colors, font, radius, space } from "../theme";
import { Caption } from "./ui";

/**
 * Live tracking map.
 *
 * Leaflet in a WebView rather than a native map component, for one practical
 * reason: expo-maps and react-native-maps both require a Google Cloud project
 * and an API key on Android, and OpenStreetMap tiles need neither. It also
 * matches the web client exactly — same library, same tiles, same emoji
 * markers — so tracking looks like one product on both.
 *
 * The trade is performance: a WebView map is heavier than a native one. At
 * campus scale, with two markers, that isn't the constraint.
 */
export function TrackingMap({
  drop,
  runner,
  height = 240,
}: {
  drop: { lat: number; lng: number };
  runner?: { lat: number; lng: number } | null;
  height?: number;
}) {
  const webRef = useRef<WebView>(null);

  // Built once. Runner movement is pushed in via JS below rather than by
  // re-rendering the HTML, which would tear the map down on every GPS ping.
  const html = useMemo(() => buildHtml(drop, runner ?? null), [drop.lat, drop.lng]);

  // Nudge the marker on each new position.
  if (runner) {
    webRef.current?.injectJavaScript(
      `window.setRunner && window.setRunner(${runner.lat}, ${runner.lng}); true;`,
    );
  }

  return (
    <View style={[s.wrap, { height }]}>
      <WebView
        ref={webRef}
        source={{ html }}
        style={s.web}
        scrollEnabled={false}
        originWhitelist={["*"]}
        javaScriptEnabled
        // Tiles come from OSM's CDN; without this Android blocks them.
        mixedContentMode="always"
      />
      {!runner ? (
        <View style={s.badge}>
          <Caption style={s.badgeText}>📍 Drop-off point</Caption>
        </View>
      ) : (
        <View style={s.badge}>
          <Caption style={s.badgeText}>🛵 Runner is on the move</Caption>
        </View>
      )}
    </View>
  );
}

/** Self-contained Leaflet page — no bundler, no local assets. */
function buildHtml(drop: { lat: number; lng: number }, runner: { lat: number; lng: number } | null) {
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map { margin:0; padding:0; height:100%; width:100%; background:#F4F5F6; }
  .leaflet-control-attribution { font-size: 9px; }
</style>
</head>
<body>
<div id="map"></div>
<script>
  var drop = [${drop.lat}, ${drop.lng}];
  var map = L.map('map', { zoomControl: false, attributionControl: true }).setView(drop, 16);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19
  }).addTo(map);

  // Emoji markers — same as the web client, no image assets to ship.
  var dropIcon = L.divIcon({
    className: '',
    html: '<div style="font-size:28px;line-height:1;filter:drop-shadow(0 2px 2px rgba(0,0,0,.35))">📍</div>',
    iconSize: [28, 28], iconAnchor: [14, 26]
  });
  var runnerIcon = L.divIcon({
    className: '',
    html: '<div style="font-size:30px;line-height:1;filter:drop-shadow(0 2px 3px rgba(0,0,0,.4))">🛵</div>',
    iconSize: [30, 30], iconAnchor: [15, 15]
  });

  L.marker(drop, { icon: dropIcon }).addTo(map);

  var runnerMarker = null;
  window.setRunner = function (lat, lng) {
    var pos = [lat, lng];
    if (!runnerMarker) {
      runnerMarker = L.marker(pos, { icon: runnerIcon }).addTo(map);
    } else {
      runnerMarker.setLatLng(pos);
    }
    // Keep both the runner and the destination in frame as they close in.
    map.fitBounds(L.latLngBounds([pos, drop]).pad(0.35), { animate: true });
  };

  ${runner ? `window.setRunner(${runner.lat}, ${runner.lng});` : ""}
</script>
</body>
</html>`;
}

const s = StyleSheet.create({
  wrap: {
    marginTop: space.lg,
    borderRadius: radius.xl,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.bgSoft,
  },
  web: { flex: 1, backgroundColor: "transparent" },
  badge: {
    position: "absolute",
    left: space.md,
    top: space.md,
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: 5,
  },
  badgeText: { color: colors.ink, fontFamily: font.semi, fontSize: font.tiny },
});
