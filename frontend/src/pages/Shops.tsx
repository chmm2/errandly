import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchVendors } from "../api/vendors";
import Navbar from "../components/Navbar";

const CATEGORY_ICONS: Record<string, string> = {
  FOOD: "🍔",
  GROCERY: "🛒",
  STATIONERY: "📚",
  PHARMACY: "💊",
};

export default function Shops() {
  const { data: vendors } = useQuery({ queryKey: ["vendors"], queryFn: fetchVendors });

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <section className="bg-gradient-to-br from-brand to-brand-dark text-white">
        <div className="mx-auto max-w-6xl px-4 py-12">
          <h1 className="text-3xl font-extrabold sm:text-4xl">Campus stores 🏪</h1>
          <p className="mt-2 max-w-xl text-white/90">
            Order straight off the menu — a runner picks it up and brings it to you.
          </p>
        </div>
      </section>

      <div className="mx-auto max-w-6xl px-4 py-10">
        {(vendors ?? []).length === 0 ? (
          <div className="rounded-2xl border-2 border-dashed border-line p-12 text-center text-muted">
            No stores onboarded yet — the admin adds them.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {vendors!.map((v) => (
              <Link
                key={v.id}
                to={`/shops/${v.id}`}
                className={`group rounded-2xl border border-line p-5 transition hover:-translate-y-1 hover:border-brand hover:shadow-lg ${
                  v.is_open ? "" : "opacity-60"
                }`}
              >
                <div className="text-4xl">{CATEGORY_ICONS[v.category] ?? "🏪"}</div>
                <div className="mt-3 font-bold group-hover:text-brand">{v.name}</div>
                {v.description && (
                  <div className="mt-1 line-clamp-2 text-sm text-muted">{v.description}</div>
                )}
                <div
                  className={`mt-2 inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${
                    v.is_open ? "bg-green-50 text-green-700" : "bg-gray-100 text-muted"
                  }`}
                >
                  {v.is_open ? "● Open" : "Closed"}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
