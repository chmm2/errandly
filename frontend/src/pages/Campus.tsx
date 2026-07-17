import { MapContainer, TileLayer } from "react-leaflet";
import { Link } from "react-router-dom";

import CampusOverlay from "../components/CampusOverlay";
import Navbar from "../components/Navbar";
import { CAMPUS_CENTER, campusPois, POI_ICONS } from "../data/campus";

import "leaflet/dist/leaflet.css";

export default function Campus() {
  const pois = campusPois();
  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <div className="mx-auto max-w-4xl px-4 py-8">
        <Link to="/" className="text-sm font-semibold text-muted hover:text-brand">
          ← Back
        </Link>
        <h1 className="mt-2 text-3xl font-extrabold">Campus map 🗺️</h1>
        <p className="mt-1 text-muted">
          Our own map — boundary, walking routes and every spot that matters, including places
          Google Maps doesn't show. Used across the app to pick exact drop points.
        </p>

        <div className="mt-6 overflow-hidden rounded-2xl border border-line shadow-sm">
          <MapContainer
            center={CAMPUS_CENTER}
            zoom={16}
            style={{ height: 420, width: "100%" }}
            scrollWheelZoom={false}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <CampusOverlay />
          </MapContainer>
        </div>

        <h2 className="mt-8 text-xl font-extrabold">Spots</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {pois.map((p) => (
            <div
              key={p.name}
              className="flex items-center gap-3 rounded-xl border border-line px-4 py-3"
            >
              <span className="text-2xl">{POI_ICONS[p.category]}</span>
              <span className="text-sm font-semibold">{p.name}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
