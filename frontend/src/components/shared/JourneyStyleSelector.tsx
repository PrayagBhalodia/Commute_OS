"use client";

import { Armchair, IndianRupee, Zap } from "lucide-react";
import { PRIORITY_LABELS, TRIP_PRIORITIES, type TripPriority } from "@/lib/priority";
import { cn } from "@/lib/utils";
import { useJourneyStore } from "@/store/journey-store";

// Single source of truth for the Time / Cost / Comfort journey styles shown
// in the Travel DNA page and the account menu. Both variants read and write
// the shared store priority, so they stay in sync with the Plan page by
// construction.
const STYLE_META: Record<
  TripPriority,
  { icon: typeof Zap; description: string; activeClass: string }
> = {
  time: {
    icon: Zap,
    description: "Prioritise the fastest arrival across every leg.",
    activeClass: "border-sky-500 bg-sky-50 text-sky-700",
  },
  cost: {
    icon: IndianRupee,
    description: "Favour the most affordable combination of legs.",
    activeClass: "border-amber-500 bg-amber-50 text-amber-700",
  },
  comfort: {
    icon: Armchair,
    description: "Prefer the smoothest, most comfortable ride.",
    activeClass: "border-violet-500 bg-violet-50 text-violet-700",
  },
};

export function JourneyStyleSelector({
  variant = "cards",
  onSelect,
}: {
  /** "cards" shows icon + description tiles; "segmented" is the compact pill row. */
  variant?: "cards" | "segmented";
  onSelect?: (priority: TripPriority) => void;
}) {
  const priority = useJourneyStore((state) => state.priority);
  const setPriority = useJourneyStore((state) => state.setPriority);

  const choose = (next: TripPriority) => {
    setPriority(next);
    onSelect?.(next);
  };

  if (variant === "segmented") {
    return (
      <div
        className="grid grid-cols-3 gap-1 rounded-md bg-slate-100 p-1"
        role="group"
        aria-label="Journey style"
      >
        {TRIP_PRIORITIES.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={priority === option}
            className={cn(
              "focus-ring rounded px-2 py-1.5",
              priority === option
                ? "bg-white font-medium text-slate-950 shadow-sm"
                : "text-slate-600",
            )}
            onClick={() => choose(option)}
          >
            {PRIORITY_LABELS[option]}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-3" role="group" aria-label="Journey style">
      {TRIP_PRIORITIES.map((option) => {
        const meta = STYLE_META[option];
        const Icon = meta.icon;
        const active = priority === option;
        return (
          <button
            key={option}
            type="button"
            aria-pressed={active}
            onClick={() => choose(option)}
            className={cn(
              "flex flex-col items-start gap-2 rounded-lg border p-4 text-left transition",
              active ? meta.activeClass : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100",
            )}
          >
            <span className="flex items-center gap-2 text-sm font-semibold">
              <Icon className="h-4 w-4" />
              {PRIORITY_LABELS[option]}
            </span>
            <span className="text-xs leading-relaxed text-slate-500">{meta.description}</span>
          </button>
        );
      })}
    </div>
  );
}
