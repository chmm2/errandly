import L from "leaflet";
import { useState } from "react";
import { MapContainer, Marker, TileLayer, useMapEvents } from "react-leaflet";

import { CAMPUS_CENTER } from "../data/campus";
import CampusOverlay from "./CampusOverlay";

import "leaflet/dist/leaflet.css";

const pinIcon = L.divIcon({
  className: "",
  html: '<div style="font-size:30px;line-height:1;filter:drop-shadow(0 2px 3px rgba(0,0,0,.4))">📍</div>',
  iconSize: [30, 30],
  iconAnchor: [15, 28],
});

interface Selection {
  lat: number;
  lng: number;
  label: string;
}

function ClickToDrop({ onDrop }: { onDrop: (lat: number, lng: number) => void }) {
  useMapEvents({ click: (e) => onDrop(e.latlng.lat, e.latlng.lng) });
  return null;
}

/** Tap a named spot (or anywhere) on the campus map to set the drop point. */
export default function CampusDropPicker({
  onConfirm,
}: {
  onConfirm: (sel: Selection) => void;
}) {
  const [sel, setSel] = useState<Selection | null>(null);

  return (
    <div className="overflow-hidden rounded-2xl border border-line">
      <MapContainer center={CAMPUS_CENTER} zoom={16} style={{ height: 320, width: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <CampusOverlay
          onPickPoi={(p) => setSel({ lat: p.lat, lng: p.lng, label: p.name })}
        />
        <ClickToDrop
          onDrop={(lat, lng) =>
            setSel({ lat, lng, label: `Pinned spot (${lat.toFixed(4)}, ${lng.toFixed(4)})` })
          }
        />
        {sel && <Marker position={[sel.lat, sel.lng]} icon={pinIcon} />}
      </MapContainer>
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white px-4 py-3">
        <div className="min-w-0 text-sm">
          {sel ? (
            <span className="font-semibold text-ink">📍 {sel.label}</span>
          ) : (
            <span className="text-muted">Tap a spot, or anywhere on the map</span>
          )}
        </div>
        <button
          type="button"
          disabled={!sel}
          onClick={() => sel && onConfirm(sel)}
          className="rounded-xl bg-brand px-5 py-2 text-sm font-bold text-white transition hover:bg-brand-dark disabled:opacity-50"
        >
          Use this spot
        </button>
      </div>
    </div>
  );
}
