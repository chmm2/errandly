import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { fetchMe, setPhoto } from "../api/auth";
import { type Errand, fetchMyErrands, rateErrand } from "../api/errands";
import Navbar from "../components/Navbar";
import { useAuth } from "../stores/auth";

const CATEGORY_ICONS: Record<string, string> = {
  FOOD: "🍔",
  GROCERY: "🛒",
  PARCEL: "📦",
  STATIONERY: "📚",
  PHARMACY: "💊",
  CUSTOM: "🛺",
};

const TERMINAL = ["COMPLETED", "CANCELLED", "EXPIRED"];
const STATUS_LABEL: Record<string, string> = {
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
  EXPIRED: "Expired",
};

/** Center-crop + shrink an image to a tiny square data URL — same trick the
 * runner page uses so avatars stay a few KB with no object storage. */
function resizeImage(file: File, size = 128): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = size;
      const ctx = canvas.getContext("2d");
      if (!ctx) return reject(new Error("no canvas"));
      const min = Math.min(img.width, img.height);
      ctx.drawImage(img, (img.width - min) / 2, (img.height - min) / 2, min, min, 0, 0, size, size);
      URL.revokeObjectURL(img.src);
      resolve(canvas.toDataURL("image/jpeg", 0.8));
    };
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });
}

function RatingModal({ errandId, onDone }: { errandId: string; onDone: () => void }) {
  const [stars, setStars] = useState(0);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    try {
      await rateErrand(errandId, stars);
    } finally {
      onDone();
    }
  }
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-sm rounded-3xl bg-white p-6 text-center shadow-2xl">
        <div className="text-4xl">🎉</div>
        <h3 className="mt-2 text-xl font-extrabold">Rate your runner</h3>
        <div className="mt-4 flex justify-center gap-1 text-4xl">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} onClick={() => setStars(n)} aria-label={`${n} stars`}>
              {n <= stars ? "★" : "☆"}
            </button>
          ))}
        </div>
        <div className="mt-5 flex gap-3">
          <button
            onClick={onDone}
            className="flex-1 rounded-xl border border-line py-2.5 font-semibold text-muted"
          >
            Skip
          </button>
          <button
            onClick={submit}
            disabled={stars === 0 || busy}
            className="flex-1 rounded-xl bg-brand py-2.5 font-bold text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}

function HistoryRow({
  errand,
  role,
  onRate,
}: {
  errand: Errand;
  role: "requested" | "ran";
  onRate: (id: string) => void;
}) {
  const when = new Date(errand.completed_at ?? errand.cancelled_at ?? errand.created_at);
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-line p-4">
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-xl">
        {CATEGORY_ICONS[errand.category] ?? "✨"}
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate font-bold">{errand.title}</div>
        <div className="mt-0.5 truncate text-sm text-muted">
          {role === "ran" ? "You ran this" : "You ordered"} ·{" "}
          {when.toLocaleDateString(undefined, { day: "numeric", month: "short" })} · ₹
          {Number(errand.reward).toFixed(0)}
        </div>
      </div>
      <span className="shrink-0 rounded-full bg-gray-100 px-3 py-1 text-xs font-bold text-muted">
        {STATUS_LABEL[errand.status] ?? errand.status}
      </span>
      {role === "requested" && errand.status === "COMPLETED" && !errand.rated && (
        <button
          onClick={() => onRate(errand.id)}
          className="shrink-0 rounded-xl border border-brand px-3 py-1.5 text-sm font-bold text-brand transition hover:bg-brand-soft"
        >
          Rate ★
        </button>
      )}
    </div>
  );
}

export default function Profile() {
  const user = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setUser);
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [ratingFor, setRatingFor] = useState<string | null>(null);

  useQuery({ queryKey: ["me"], queryFn: fetchMe }); // keep the store fresh
  const { data: mine } = useQuery({ queryKey: ["my-errands"], queryFn: fetchMyErrands });

  const requestedHistory = (mine?.requested ?? []).filter((e) => TERMINAL.includes(e.status));
  const ranHistory = (mine?.running ?? []).filter((e) => TERMINAL.includes(e.status));
  const history = [
    ...requestedHistory.map((e) => ({ e, role: "requested" as const })),
    ...ranHistory.map((e) => ({ e, role: "ran" as const })),
  ].sort(
    (a, b) =>
      new Date(b.e.completed_at ?? b.e.cancelled_at ?? b.e.created_at).getTime() -
      new Date(a.e.completed_at ?? a.e.cancelled_at ?? a.e.created_at).getTime(),
  );

  const photo = useMutation({
    mutationFn: (dataUrl: string) => setPhoto(dataUrl),
    onSuccess: (u) => setUser(u),
  });

  async function onPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      photo.mutate(await resizeImage(file));
    } catch {
      /* ignore bad image */
    }
  }

  return (
    <div className="min-h-screen bg-white">
      <Navbar />

      {/* Profile header */}
      <section className="bg-gradient-to-br from-brand to-brand-dark text-white">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-5 px-4 py-10">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            title="Change your photo"
            className="relative shrink-0"
          >
            {user?.photo_url ? (
              <img
                src={user.photo_url}
                alt={user.display_name}
                className="h-20 w-20 rounded-full object-cover ring-4 ring-white/40"
              />
            ) : (
              <span className="flex h-20 w-20 items-center justify-center rounded-full bg-white/20 text-2xl font-extrabold ring-4 ring-white/40">
                {(user?.display_name ?? "?").charAt(0).toUpperCase()}
              </span>
            )}
            <span className="absolute -bottom-1 -right-1 rounded-full bg-white px-2 py-0.5 text-xs font-bold text-brand">
              {photo.isPending ? "…" : "📷"}
            </span>
          </button>
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onPhoto} />
          <div>
            <h1 className="text-3xl font-extrabold">{user?.display_name}</h1>
            <p className="mt-1 text-white/85">
              ★ {Number(user?.reputation_score ?? 0).toFixed(1)}
              {user?.student_id ? ` · ${user.student_id}` : ""}
            </p>
            <p className="text-sm text-white/70">{user?.email}</p>
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-4xl space-y-10 px-4 py-10">
        {/* History */}
        <section>
          <h2 className="text-xl font-extrabold">History</h2>
          {history.length === 0 ? (
            <div className="mt-3 rounded-2xl border-2 border-dashed border-line p-10 text-center text-muted">
              Nothing here yet — your past errands and runs will collect here.
            </div>
          ) : (
            <div className="mt-3 space-y-3">
              {history.map(({ e, role }) => (
                <HistoryRow key={e.id} errand={e} role={role} onRate={setRatingFor} />
              ))}
            </div>
          )}
        </section>
      </div>

      {ratingFor && (
        <RatingModal
          errandId={ratingFor}
          onDone={() => {
            setRatingFor(null);
            queryClient.invalidateQueries({ queryKey: ["my-errands"] });
          }}
        />
      )}
    </div>
  );
}
