import type { Feature, FeatureCollection, Point } from "geojson";

/**
 * Campus map data — a hand-authored overlay Google Maps doesn't have:
 * the campus boundary, internal walking routes, and named spots.
 *
 * ── HOW YOUR TEAM REPLACES THIS WITH THE REAL CAMPUS ──────────────────
 * 1. Open https://geojson.io
 * 2. Trace the campus boundary (polygon), the internal paths (lines), and
 *    drop a marker on every spot (gates, canteens, blocks, parcel point,
 *    hostels).
 * 3. On each feature set a property `kind`:
 *      boundary polygon → { "kind": "boundary" }
 *      each path line   → { "kind": "path" }
 *      each spot marker → { "kind": "poi", "name": "Main Gate",
 *                           "category": "gate" }
 *    categories: gate | food | academic | hostel | parcel | other
 * 4. Export as GeoJSON and paste the `features` array below.
 *
 * The coordinates here are APPROXIMATE PLACEHOLDERS around VIT Vellore so the
 * map isn't empty — swap them for your traced data. Note GeoJSON order is
 * [longitude, latitude].
 */

export const CAMPUS_CENTER: [number, number] = [12.9692, 79.1559]; // [lat, lng]

export type PoiCategory = "gate" | "food" | "academic" | "hostel" | "parcel" | "other";

export const POI_ICONS: Record<PoiCategory, string> = {
  gate: "🚪",
  food: "🍔",
  academic: "🏛️",
  hostel: "🏠",
  parcel: "📦",
  other: "📍",
};

function poi(name: string, category: PoiCategory, lat: number, lng: number): Feature<Point> {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [lng, lat] },
    properties: { kind: "poi", name, category },
  };
}

export const campusGeo: FeatureCollection = {
  type: "FeatureCollection",
  features: [
    // --- boundary (placeholder rectangle) ---
    {
      type: "Feature",
      properties: { kind: "boundary" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [79.1508, 12.9648],
            [79.1610, 12.9648],
            [79.1610, 12.9736],
            [79.1508, 12.9736],
            [79.1508, 12.9648],
          ],
        ],
      },
    },
    // --- an internal path (placeholder) ---
    {
      type: "Feature",
      properties: { kind: "path" },
      geometry: {
        type: "LineString",
        coordinates: [
          [79.1520, 12.9662],
          [79.1559, 12.9692],
          [79.1585, 12.9715],
        ],
      },
    },
    // --- named spots (placeholder coordinates) ---
    poi("Main Gate", "gate", 12.9662, 79.152),
    poi("Foodys / Food Court", "food", 12.9689, 79.1548),
    poi("SJT Block", "academic", 12.9705, 79.1562),
    poi("Parcel Collection Point", "parcel", 12.9671, 79.1535),
    poi("Men's Hostel Block", "hostel", 12.9718, 79.1585),
    poi("Ladies' Hostel Block", "hostel", 12.9666, 79.1588),
    poi("Health Centre", "other", 12.9698, 79.1522),
  ],
};

export interface CampusPoi {
  name: string;
  category: PoiCategory;
  lat: number;
  lng: number;
}

/** Pull the POI spots out of the GeoJSON for lists / pickers. */
export function campusPois(fc: FeatureCollection = campusGeo): CampusPoi[] {
  return fc.features
    .filter((f) => f.properties?.kind === "poi" && f.geometry.type === "Point")
    .map((f) => {
      const [lng, lat] = (f.geometry as Point).coordinates;
      return {
        name: (f.properties?.name as string) ?? "Spot",
        category: (f.properties?.category as PoiCategory) ?? "other",
        lat,
        lng,
      };
    });
}
