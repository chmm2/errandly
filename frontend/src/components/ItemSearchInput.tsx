import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { searchReferences, type ReferenceSuggestion } from "../api/fraud";

interface Props {
  value: string;
  placeholder?: string;
  /** Set once the line is bound to a priced item; cleared when edited away. */
  picked: ReferenceSuggestion | null;
  onChange: (name: string) => void;
  onPick: (s: ReferenceSuggestion | null) => void;
  className?: string;
}

/**
 * Shopping-list line input with type-ahead over the admin's non-MRP list.
 *
 * Picking a suggestion is what makes the line priced, and a priced line is the
 * only kind that earns escrow headroom. Typing freely is still allowed - not
 * everything on a shelf has been priced by an admin yet - so the control has
 * to make the difference visible rather than silently accepting either.
 */
export default function ItemSearchInput({
  value, placeholder, picked, onChange, onPick, className = "",
}: Props) {
  const [open, setOpen] = useState(false);
  const [debounced, setDebounced] = useState(value);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  // Debounced so a fast typist does not fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), 180);
    return () => clearTimeout(t);
  }, [value]);

  useEffect(() => {
    function away(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);

  const { data: hits = [] } = useQuery({
    queryKey: ["ref-search", debounced],
    queryFn: () => searchReferences(debounced),
    enabled: open && debounced.trim().length > 0,
    staleTime: 60_000,
  });

  function choose(s: ReferenceSuggestion) {
    onChange(s.display_name);
    onPick(s);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open || hits.length === 0) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => (a + 1) % hits.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => (a - 1 + hits.length) % hits.length); }
    else if (e.key === "Enter") { e.preventDefault(); choose(hits[active] ?? hits[0]); }
    else if (e.key === "Escape") setOpen(false);
  }

  return (
    <div ref={boxRef} className={`relative ${className}`}>
      <input
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          // Editing the text breaks the binding: the price must never outlive
          // the name it was quoted for.
          if (picked) onPick(null);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        className="w-full rounded-xl border border-line px-4 py-3 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20"
        autoComplete="off"
      />

      {picked && (
        <div className="mt-1 flex items-center gap-2 text-xs">
          <span className="rounded-full bg-brand-soft px-2 py-0.5 font-bold text-brand-dark">
            ₹{picked.reference_price.toFixed(0)} each
          </span>
          <span className="text-muted">
            campus price · runner may pay ₹{picked.band_min.toFixed(0)}–
            {picked.band_max.toFixed(0)}
          </span>
        </div>
      )}

      {open && hits.length > 0 && (
        <ul className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-xl border border-line bg-white shadow-lg">
          {hits.map((s, i) => (
            <li key={s.reference_id}>
              <button
                type="button"
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(s)}
                className={`flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left ${
                  i === active ? "bg-brand-soft" : "hover:bg-neutral-50"
                }`}
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold">
                    {s.display_name}
                  </span>
                  {s.matched_via && (
                    <span className="block truncate text-xs text-muted">
                      also known as “{s.matched_via}”
                    </span>
                  )}
                </span>
                <span className="shrink-0 text-sm font-bold text-brand-dark">
                  ₹{s.reference_price.toFixed(0)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && debounced.trim() !== "" && hits.length === 0 && value.trim() !== "" && (
        <div className="absolute z-30 mt-1 w-full rounded-xl border border-line bg-white px-4 py-2.5 text-xs text-muted shadow-lg">
          Not on the campus price list — the runner will pay the shelf price and
          report it.
        </div>
      )}
    </div>
  );
}
