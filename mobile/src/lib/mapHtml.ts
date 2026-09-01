/** Self-contained Leaflet page — no bundler, no local assets. */
export function buildMapHtml(drop: { lat: number; lng: number }, runner: { lat: number; lng: number } | null) {
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
