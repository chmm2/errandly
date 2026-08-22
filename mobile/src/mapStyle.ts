/**
 * Google Maps style JSON, in the format Snazzy Maps exports.
 *
 * To use your own: open your style on snazzymaps.com, copy the JSON array from
 * the "JavaScript Style Array" box, and replace everything between the
 * brackets below. Nothing else needs to change.
 *
 * What's here now is a restrained light style tuned to the app's palette —
 * muted land, soft orange roads, calm water — so the 📍 and 🛵 markers stay the
 * loudest thing on screen. A map you have to hunt for the pin on is a map
 * that's fighting its own content.
 */
export const MAP_STYLE = [
  { elementType: "geometry", stylers: [{ color: "#F7F7F8" }] },
  { elementType: "labels.icon", stylers: [{ visibility: "off" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#686B78" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#FFFFFF" }] },

  { featureType: "administrative", elementType: "geometry", stylers: [{ visibility: "off" }] },
  {
    featureType: "administrative.land_parcel",
    elementType: "labels",
    stylers: [{ visibility: "off" }],
  },

  { featureType: "poi", elementType: "labels.text", stylers: [{ visibility: "off" }] },
  { featureType: "poi.business", stylers: [{ visibility: "off" }] },
  { featureType: "poi.park", elementType: "geometry", stylers: [{ color: "#E6F0E4" }] },

  // Roads warm slightly toward the brand so the map feels part of the app.
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#FFFFFF" }] },
  { featureType: "road.arterial", elementType: "geometry", stylers: [{ color: "#FFF4EA" }] },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#FFE3C7" }] },
  { featureType: "road.local", elementType: "labels", stylers: [{ visibility: "off" }] },

  { featureType: "transit", stylers: [{ visibility: "off" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#D9E6EF" }] },
  { featureType: "water", elementType: "labels.text", stylers: [{ visibility: "off" }] },
];
