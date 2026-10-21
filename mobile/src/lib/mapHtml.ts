/** Self-contained Leaflet page: no bundler, no local assets. */
export function buildMapHtml(drop: { lat: number; lng: number }, runner: { lat: number; lng: number } | null) {
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map { margin:0; padding:0; height:100%; width:100%; background:#EAF0EE; }
  .leaflet-control-attribution { font-size: 9px; }
  /* The route marches toward the drop-off, the design's cue that it is live. */
  @keyframes dash { to { stroke-dashoffset: -34; } }
  .route { animation: dash 1.6s linear infinite; }
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

  // Drawn markers from the app's own icon set, so the map carries no emoji.
  // The runner is the bike glyph in a ringed white disc; the drop-off is a
  // teal dot with a faint halo, exactly as the design draws its map.
  var BIKE = '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="#274A4C" ' +
    'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' +
    '<circle cx="6.4" cy="16.6" r="2.9"/><circle cx="17.6" cy="16.6" r="2.9"/>' +
    '<path d="M6.4 16.6 10 9h4l2.6 7.6"/><path d="M13 9h3.6"/></svg>';

  var dropIcon = L.divIcon({
    className: '',
    html: '<svg width="26" height="26" viewBox="0 0 26 26">' +
      '<circle cx="13" cy="13" r="12" fill="none" stroke="#274A4C" stroke-width="1.5" opacity=".4"/>' +
      '<circle cx="13" cy="13" r="6" fill="#274A4C"/></svg>',
    iconSize: [26, 26], iconAnchor: [13, 13]
  });
  var runnerIcon = L.divIcon({
    className: '',
    html: '<div style="width:34px;height:34px;border-radius:50%;background:#fff;' +
      'border:2px solid #274A4C;box-sizing:border-box;display:flex;align-items:center;' +
      'justify-content:center;box-shadow:0 6px 14px -6px rgba(23,32,31,.5)">' + BIKE + '</div>',
    iconSize: [34, 34], iconAnchor: [17, 17]
  });

  L.marker(drop, { icon: dropIcon }).addTo(map);

  var runnerMarker = null;
  var route = null;
  window.setRunner = function (lat, lng) {
    var pos = [lat, lng];
    if (!runnerMarker) {
      route = L.polyline([pos, drop], {
        color: '#274A4C', weight: 3, dashArray: '9 8', lineCap: 'round', className: 'route'
      }).addTo(map);
      runnerMarker = L.marker(pos, { icon: runnerIcon }).addTo(map);
    } else {
      runnerMarker.setLatLng(pos);
      route.setLatLngs([pos, drop]);
    }
    // Keep both the runner and the destination in frame as they close in.
    map.fitBounds(L.latLngBounds([pos, drop]).pad(0.35), { animate: true });
  };

  ${runner ? `window.setRunner(${runner.lat}, ${runner.lng});` : ""}
</script>
</body>
</html>`;
}
