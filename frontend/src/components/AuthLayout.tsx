import type { ReactNode } from "react";

const STATS = [
  { value: "2 km", label: "average trip to the campus gate — gone" },
  { value: "100%", label: "verified students, both sides of every errand" },
  { value: "< 30 min", label: "typical delivery, matched by live location" },
];

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      {/* Brand panel */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-gradient-to-br from-brand to-brand-dark p-12 text-white lg:flex">
        <div className="flex items-center gap-2">
          <span className="text-3xl">🛵</span>
          <span className="text-2xl font-extrabold tracking-tight">errandly</span>
        </div>

        <div>
          <h1 className="max-w-md text-5xl font-extrabold leading-tight">
            Campus errands, delivered by students.
          </h1>
          <p className="mt-4 max-w-md text-lg text-white/90">
            Food runs, grocery trips, parcel pickups from the collection point — post it, and a
            verified runner heading that way picks it up.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-6">
          {STATS.map((s) => (
            <div key={s.value}>
              <div className="text-3xl font-extrabold">{s.value}</div>
              <div className="mt-1 text-sm text-white/80">{s.label}</div>
            </div>
          ))}
        </div>

        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/10" />
        <div className="pointer-events-none absolute -bottom-32 -left-16 h-96 w-96 rounded-full bg-white/10" />
      </div>

      {/* Form panel */}
      <div className="flex w-full items-center justify-center bg-white px-6 py-12 lg:w-1/2">
        <div className="w-full max-w-md">{children}</div>
      </div>
    </div>
  );
}
