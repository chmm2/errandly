import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import {
  createSlot,
  deleteSlot,
  fetchSlots,
  setVitSlots,
  type TimetableSlot,
} from "../api/timetable";
import Navbar from "../components/Navbar";
import { apiErrorMessage } from "../lib/api";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const inputCls =
  "w-full rounded-xl border border-line px-4 py-3 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20";

function toMinutes(time: string): number {
  const [h, m] = time.split(":").map(Number);
  return h * 60 + m;
}

function toTime(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

export default function Timetable() {
  const queryClient = useQueryClient();
  const [day, setDay] = useState(0);
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("09:50");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [raw, setRaw] = useState("");
  const [unknown, setUnknown] = useState<string[]>([]);

  const { data: slots } = useQuery({ queryKey: ["timetable"], queryFn: fetchSlots });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["timetable"] });
  const add = useMutation({
    mutationFn: createSlot,
    onSuccess: () => {
      setLabel("");
      setError(null);
      refresh();
    },
    onError: (err) => setError(apiErrorMessage(err, "Could not add the slot.")),
  });
  const remove = useMutation({ mutationFn: deleteSlot, onSettled: refresh });

  const applyVit = useMutation({
    // Tokenise the pasted slots on anything that isn't a letter/number
    // (so "B2+TB2 L11+L12, C2" all works), then replace the timetable.
    mutationFn: () => setVitSlots(raw.split(/[^A-Za-z0-9]+/).filter(Boolean)),
    onSuccess: (res) => {
      setError(null);
      setUnknown(res.unknown);
      setRaw("");
      refresh();
    },
    onError: (err) => setError(apiErrorMessage(err, "Could not read those slots.")),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    add.mutate({
      day_of_week: day,
      start_minute: toMinutes(start),
      end_minute: toMinutes(end),
      label: label.trim(),
    });
  }

  const byDay = (slots ?? []).reduce<Record<number, TimetableSlot[]>>((acc, s) => {
    (acc[s.day_of_week] ??= []).push(s);
    return acc;
  }, {});

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <div className="mx-auto max-w-3xl px-4 py-8">
        <Link to="/" className="text-sm font-semibold text-muted hover:text-brand">
          ← Back
        </Link>
        <h1 className="mt-2 text-3xl font-extrabold">My timetable 🗓️</h1>
        <p className="mt-1 text-muted">
          Enter your VIT slots and Errandly keeps you honest: runner mode locks itself during
          class — you can't go online, offers skip you, and if a class starts while you're online
          you're taken offline automatically.
        </p>

        {error && (
          <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Primary: paste VIT slots from VTOP */}
        <div className="mt-6 rounded-2xl border border-line bg-brand-soft/40 p-5">
          <label htmlFor="vit" className="block font-bold">
            Paste your VIT slots
          </label>
          <p className="mt-1 text-sm text-muted">
            Copy the slot codes from your VTOP timetable — theory and lab. Separate them any way
            you like. Example:{" "}
            <span className="font-mono text-ink">A2+TA2 B2+TB2 L11+L12 C2+TC2</span>
          </p>
          <textarea
            id="vit"
            rows={2}
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder="A2+TA2  B2+TB2  L11+L12  C2+TC2  D2+TD2 …"
            className={`${inputCls} mt-3 font-mono`}
          />
          <div className="mt-3 flex items-center gap-3">
            <button
              onClick={() => applyVit.mutate()}
              disabled={applyVit.isPending || !raw.trim()}
              className="rounded-xl bg-brand px-6 py-3 font-bold text-white transition hover:bg-brand-dark disabled:opacity-60"
            >
              {applyVit.isPending ? "Loading…" : "Load my timetable"}
            </button>
            <span className="text-xs text-muted">This replaces your current timetable.</span>
          </div>
          {unknown.length > 0 && (
            <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
              Didn't recognise: <span className="font-mono">{unknown.join(", ")}</span> — check the
              spelling against your VTOP.
            </div>
          )}
        </div>

        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-semibold text-muted hover:text-brand">
            or add a custom time block
          </summary>
          <form
            onSubmit={onSubmit}
            className="mt-3 grid gap-3 rounded-2xl border border-line p-5 sm:grid-cols-[1.2fr_1fr_1fr_1.4fr_auto]"
          >
          <select
            value={day}
            onChange={(e) => setDay(Number(e.target.value))}
            className={inputCls}
            aria-label="Day"
          >
            {DAYS.map((d, i) => (
              <option key={d} value={i}>
                {d}
              </option>
            ))}
          </select>
          <input
            type="time"
            required
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className={inputCls}
            aria-label="Start time"
          />
          <input
            type="time"
            required
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className={inputCls}
            aria-label="End time"
          />
          <input
            required
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Course, e.g. CSE3001"
            maxLength={120}
            className={inputCls}
          />
          <button
            type="submit"
            disabled={add.isPending}
            className="rounded-xl bg-brand px-5 py-3 font-bold text-white transition hover:bg-brand-dark disabled:opacity-60"
          >
            Add
          </button>
          </form>
        </details>

        <div className="mt-8 space-y-6">
          {DAYS.map((dayName, i) =>
            (byDay[i] ?? []).length === 0 ? null : (
              <div key={dayName}>
                <h2 className="font-extrabold">{dayName}</h2>
                <div className="mt-2 space-y-2">
                  {byDay[i]
                    .sort((a, b) => a.start_minute - b.start_minute)
                    .map((slot) => (
                      <div
                        key={slot.id}
                        className="flex items-center justify-between rounded-xl border border-line px-4 py-3"
                      >
                        <div className="flex items-center gap-4">
                          <span className="rounded-lg bg-brand-soft px-2.5 py-1 text-sm font-bold text-brand-dark">
                            {toTime(slot.start_minute)}–{toTime(slot.end_minute)}
                          </span>
                          <span className="font-semibold">{slot.label}</span>
                        </div>
                        <button
                          onClick={() => remove.mutate(slot.id)}
                          disabled={remove.isPending}
                          className="text-sm font-semibold text-muted transition hover:text-red-600"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                </div>
              </div>
            ),
          )}
          {(slots ?? []).length === 0 && (
            <div className="rounded-2xl border-2 border-dashed border-line p-10 text-center text-muted">
              No classes yet — add your first slot above.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
