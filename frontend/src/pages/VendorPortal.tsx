import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import {
  addMenuItem,
  deleteMenuItem,
  fetchMyStore,
  type MenuItem,
  updateMenuItem,
  updateMyStore,
} from "../api/vendors";
import Navbar from "../components/Navbar";
import { apiErrorMessage } from "../lib/api";
import { api } from "../lib/api";

const inputCls =
  "w-full rounded-xl border border-line px-4 py-3 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20";

async function fetchMyMenu(vendorId: string): Promise<MenuItem[]> {
  return (await api.get(`/vendors/${vendorId}/menu`)).data.items;
}

export default function VendorPortal() {
  const queryClient = useQueryClient();
  const [section, setSection] = useState("");
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: store } = useQuery({ queryKey: ["my-store"], queryFn: fetchMyStore });
  const { data: items } = useQuery({
    queryKey: ["my-menu", store?.id],
    queryFn: () => fetchMyMenu(store!.id),
    enabled: !!store,
  });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["my-store"] });
    queryClient.invalidateQueries({ queryKey: ["my-menu"] });
  }

  const toggleStore = useMutation({
    mutationFn: (open: boolean) => updateMyStore({ is_open: open }),
    onSettled: refresh,
  });
  const add = useMutation({
    mutationFn: addMenuItem,
    onSuccess: () => {
      setName("");
      setPrice("");
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, "Could not add the item.")),
    onSettled: refresh,
  });
  const toggleItem = useMutation({
    mutationFn: ({ id, available }: { id: string; available: boolean }) =>
      updateMenuItem(id, { is_available: available }),
    onSettled: refresh,
  });
  const remove = useMutation({ mutationFn: deleteMenuItem, onSettled: refresh });

  function onAdd(e: FormEvent) {
    e.preventDefault();
    add.mutate({ section: section.trim(), name: name.trim(), price: Number(price) });
  }

  const sections = new Map<string, MenuItem[]>();
  (items ?? []).forEach((i) => sections.set(i.section, [...(sections.get(i.section) ?? []), i]));

  return (
    <div className="min-h-screen bg-white">
      <Navbar />

      <section
        className={`text-white ${
          store?.is_open
            ? "bg-gradient-to-br from-emerald-500 to-emerald-700"
            : "bg-gradient-to-br from-ink to-[#3d4152]"
        }`}
      >
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-4 px-4 py-10">
          <div>
            <h1 className="text-3xl font-extrabold">{store?.name ?? "My store"} 🏪</h1>
            <p className="mt-1 text-white/85">
              {store?.is_open
                ? "You're open — students can order off your menu."
                : "You're closed — flip open when you're ready to take orders."}
            </p>
          </div>
          {store && (
            <button
              onClick={() => toggleStore.mutate(!store.is_open)}
              disabled={toggleStore.isPending}
              className={`rounded-2xl px-8 py-4 text-lg font-extrabold shadow-xl transition hover:-translate-y-0.5 disabled:opacity-60 ${
                store.is_open ? "bg-white text-emerald-700" : "bg-brand text-white"
              }`}
            >
              {store.is_open ? "Close store" : "Open store"}
            </button>
          )}
        </div>
      </section>

      <div className="mx-auto max-w-4xl px-4 py-8">
        {error && (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form
          onSubmit={onAdd}
          className="grid gap-3 rounded-2xl border border-line p-5 sm:grid-cols-[1fr_1.4fr_0.8fr_auto]"
        >
          <input
            required
            value={section}
            onChange={(e) => setSection(e.target.value)}
            placeholder="Section, e.g. Rolls"
            maxLength={80}
            className={inputCls}
          />
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Item name"
            maxLength={120}
            className={inputCls}
          />
          <input
            required
            type="number"
            min={0}
            step={1}
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="₹"
            className={inputCls}
          />
          <button
            type="submit"
            disabled={add.isPending}
            className="rounded-xl bg-brand px-5 py-3 font-bold text-white transition hover:bg-brand-dark disabled:opacity-60"
          >
            Add item
          </button>
        </form>

        <div className="mt-8 space-y-6">
          {[...sections.entries()].map(([sectionName, sectionItems]) => (
            <div key={sectionName}>
              <h2 className="font-extrabold">{sectionName}</h2>
              <div className="mt-2 space-y-2">
                {sectionItems.map((item) => (
                  <div
                    key={item.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line px-4 py-3"
                  >
                    <div className={item.is_available ? "" : "opacity-50"}>
                      <span className="font-semibold">{item.name}</span>
                      <span className="ml-3 text-sm text-muted">₹{item.price.toFixed(0)}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      {/* THE toggle: flips availability and busts the menu cache */}
                      <button
                        onClick={() =>
                          toggleItem.mutate({ id: item.id, available: !item.is_available })
                        }
                        disabled={toggleItem.isPending}
                        className={`rounded-full px-4 py-1.5 text-sm font-bold transition ${
                          item.is_available
                            ? "bg-green-50 text-green-700 hover:bg-green-100"
                            : "bg-red-50 text-red-600 hover:bg-red-100"
                        }`}
                      >
                        {item.is_available ? "In stock" : "Sold out"}
                      </button>
                      <button
                        onClick={() => remove.mutate(item.id)}
                        className="text-sm font-semibold text-muted transition hover:text-red-600"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {(items ?? []).length === 0 && (
            <div className="rounded-2xl border-2 border-dashed border-line p-10 text-center text-muted">
              Your menu is empty — add your first item above.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
