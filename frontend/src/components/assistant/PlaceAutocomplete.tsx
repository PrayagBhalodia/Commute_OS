"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, MapPin, Search } from "lucide-react";
import type { PlaceInfo } from "@/models/journey";
import { placeLabel, searchPlaces } from "@/services/places-service";

/**
 * Debounced place autocomplete used when the assistant is collecting an
 * origin/destination. Picking a suggestion submits a precise place (e.g.
 * "Thaltej, Ahmedabad") so the backend never has to guess or drill down a
 * broad/misspelled free-text answer. Enter still submits whatever was typed.
 */
export function PlaceAutocomplete({
  placeholder,
  onSelect,
  disabled,
}: {
  placeholder: string;
  onSelect: (value: string) => void;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<PlaceInfo[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setItems([]);
      setOpen(false);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const results = await searchPlaces(query);
        if (!cancelled) {
          setItems(results);
          setOpen(true);
          setActive(0);
        }
      } catch {
        if (!cancelled) setItems([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  // Close the dropdown on an outside click.
  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function choose(value: string) {
    const clean = value.trim();
    if (!clean) return;
    setQuery("");
    setItems([]);
    setOpen(false);
    onSelect(clean);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => Math.min(index + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const picked = open && items[active];
      choose(picked ? placeLabel(picked) : query);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={boxRef} className="relative">
      <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 focus-within:ring-2 focus-within:ring-brand-500">
        <Search className="h-4 w-4 shrink-0 text-slate-400" />
        <input
          type="text"
          value={query}
          disabled={disabled}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => items.length && setOpen(true)}
          placeholder={placeholder}
          aria-label={placeholder}
          className="w-full bg-transparent py-2 text-sm outline-none disabled:opacity-60"
        />
        {loading ? <Loader2 className="h-4 w-4 shrink-0 animate-spin text-slate-400" /> : null}
      </div>
      {open && items.length > 0 ? (
        <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border border-slate-200 bg-white py-1 shadow-lg">
          {items.map((place, index) => (
            <li key={place.place_id ?? `${place.name}-${index}`}>
              <button
                type="button"
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(placeLabel(place))}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${
                  index === active ? "bg-brand-50 text-brand-800" : "text-slate-700"
                }`}
              >
                <MapPin className="h-3.5 w-3.5 shrink-0 text-brand-500" />
                <span className="truncate">{placeLabel(place)}</span>
                {place.place_type ? (
                  <span className="ml-auto shrink-0 text-[11px] uppercase tracking-wide text-slate-400">
                    {place.place_type}
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
