import type { ReactNode } from "react";

const STATS = [
  { value: "2 km", label: "average trip to the gate — gone" },
  { value: "100%", label: "verified students, both sides" },
  { value: "< 30 min", label: "typical delivery time" },
];

const FLOATERS = [
  { emoji: "🍜", text: "Maggi from DC · ₹30", className: "left-[6%] top-[14%] animate-float" },
  { emoji: "📦", text: "Parcel pickup · ₹25", className: "right-[8%] top-[22%] animate-float-slow" },
  { emoji: "🧃", text: "Juice run · ₹20", className: "left-[10%] bottom-[18%] animate-float-slow" },
  { emoji: "💊", text: "Pharmacy dash · ₹40", className: "right-[12%] bottom-[10%] animate-float" },
];

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-brand via-[#f2670f] to-[#c2410c] px-4 py-10 sm:px-8">
      {/* Ambient shapes */}
      <div className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-white/10 blur-sm" />
      <div className="pointer-events-none absolute -bottom-40 -right-24 h-[28rem] w-[28rem] rounded-full bg-white/10" />
      <div className="pointer-events-none absolute left-1/2 top-1/3 h-64 w-64 -translate-x-1/2 rounded-full bg-yellow-300/20 blur-3xl" />

      {/* Floating errand chips — desktop garnish */}
      {FLOATERS.map((f) => (
        <div
          key={f.text}
          className={`pointer-events-none absolute hidden items-center gap-2 rounded-full bg-white/15 px-4 py-2 text-sm font-semibold text-white shadow-lg backdrop-blur-md lg:flex ${f.className}`}
        >
          <span className="text-lg">{f.emoji}</span> {f.text}
        </div>
      ))}

      <div className="relative z-10 grid w-full max-w-6xl items-center gap-10 lg:grid-cols-2 lg:gap-20">
        {/* Brand side — visible on every breakpoint */}
        <div className="text-center text-white lg:text-left">
          <div className="inline-flex items-center gap-2">
            <span className="animate-float text-4xl drop-shadow-lg lg:text-5xl">🛵</span>
            <span className="text-3xl font-extrabold tracking-tight drop-shadow lg:text-4xl">
              errandly
            </span>
          </div>

          <h1 className="mt-4 text-3xl font-extrabold leading-tight drop-shadow-sm sm:text-4xl lg:mt-8 lg:text-5xl">
            Campus errands,
            <br className="hidden lg:block" /> delivered by students.
          </h1>
          <p className="mx-auto mt-3 max-w-md text-white/90 lg:mx-0 lg:mt-5 lg:text-lg">
            Food runs, grocery trips, parcel pickups — post it, and a verified runner already
            heading that way picks it up.
          </p>

          <div className="mx-auto mt-6 grid max-w-md grid-cols-3 gap-3 lg:mx-0 lg:mt-10 lg:gap-6">
            {STATS.map((s) => (
              <div
                key={s.value}
                className="rounded-2xl bg-white/10 px-3 py-3 backdrop-blur-sm lg:bg-transparent lg:px-0 lg:py-0"
              >
                <div className="text-xl font-extrabold lg:text-3xl">{s.value}</div>
                <div className="mt-1 text-xs text-white/80 lg:text-sm">{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Form card */}
        <div className="animate-fade-up mx-auto w-full max-w-md rounded-3xl bg-white p-8 shadow-2xl shadow-black/25 ring-1 ring-black/5 sm:p-10">
          {children}
        </div>
      </div>
    </div>
  );
}
