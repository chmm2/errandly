import L from "leaflet";
import type { Feature } from "geojson";
import { GeoJSON } from "react-leaflet";

import { campusGeo, POI_ICONS, type PoiCategory } from "../data/campus";

function poiIcon(category: PoiCategory) {
  return L.divIcon({
    className: "",
    html: `<div style="font-size:24px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))">${
      POI_ICONS[category] ?? "📍"
    }</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 22],
  });
}

/** Draws the campus boundary, paths and named spots on any Leaflet map.
 * Pass onPickPoi to make the spot markers selectable (drop-point picker). */
export default function CampusOverlay({
  onPickPoi,
}: {
  onPickPoi?: (poi: { name: string; lat: number; lng: number }) => void;
}) {
  return (
    <GeoJSON
      data={campusGeo}
      style={(feature?: Feature) => {
        const kind = feature?.properties?.kind;
        if (kind === "boundary") {
          return { color: "#e8720c", weight: 2, fillColor: "#fc8019", fillOpacity: 0.06 };
        }
        return { color: "#686b78", weight: 3, dashArray: "6 6" }; // path
      }}
      pointToLayer={(feature, latlng) =>
        L.marker(latlng, {
          icon: poiIcon((feature.properties?.category as PoiCategory) ?? "other"),
          title: feature.properties?.name,
        })
      }
      onEachFeature={(feature, layer) => {
        if (feature.properties?.kind !== "poi") return;
        const name = feature.properties?.name as string;
        const [lng, lat] = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
        layer.bindTooltip(name, { direction: "top", offset: [0, -18] });
        if (onPickPoi) {
          layer.on("click", () => onPickPoi({ name, lat, lng }));
        }
      }}
    />
  );
}
