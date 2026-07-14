"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/Status";
import { cn } from "@/lib/utils";
import { useJourneyStore } from "@/store/journey-store";

// The status filters, plus an "All" that shows everything.
const TABS = ["All", "Completed", "Cancelled", "Replanned", "Refunded"] as const;
type Tab = (typeof TABS)[number];

interface TripRow {
  trip: string;
  label: string;
  status: string;
  // Which filter tabs this trip belongs to (a cancelled trip is both
  // "Cancelled" and "Refunded", etc.).
  categories: Exclude<Tab, "All">[];
}

/** Map a raw booking/disruption status into the filter categories it satisfies. */
function bookingCategories(status: string): Exclude<Tab, "All">[] {
  if (status === "cancelled") return ["Cancelled", "Refunded"];
  if (status === "partially_cancelled") return ["Completed", "Cancelled", "Refunded"];
  if (status === "confirmed") return ["Completed"];
  return [];
}

function disruptionCategories(status: string): Exclude<Tab, "All">[] {
  if (status === "cancelled_only") return ["Replanned", "Cancelled", "Refunded"];
  if (status === "rerouted") return ["Replanned", "Refunded"];
  return ["Replanned"];
}

export default function HistoryPage() {
  const plan = useJourneyStore((state) => state.activePlan);
  const booking = useJourneyStore((state) => state.booking?.booking);
  const disruption = useJourneyStore((state) => state.disruption);
  const [activeTab, setActiveTab] = useState<Tab>("All");

  const rows = useMemo<TripRow[]>(() => {
    const list: TripRow[] = [];
    if (booking) {
      list.push({
        trip: booking.trip_id,
        label: booking.status === "cancelled" ? "Cancelled journey" : "Booked journey",
        status: booking.status,
        categories: bookingCategories(booking.status),
      });
    }
    if (disruption) {
      list.push({
        trip: disruption.trip_id,
        label: "Replanned disruption",
        status: disruption.status,
        categories: disruptionCategories(disruption.status),
      });
    }
    return list;
  }, [booking, disruption]);

  const visibleRows = useMemo(
    () => (activeTab === "All" ? rows : rows.filter((row) => row.categories.includes(activeTab))),
    [rows, activeTab],
  );

  // Per-tab counts so the tabs communicate what's behind them.
  const counts = useMemo(() => {
    const map: Record<Tab, number> = { All: rows.length, Completed: 0, Cancelled: 0, Replanned: 0, Refunded: 0 };
    for (const row of rows) for (const category of row.categories) map[category] += 1;
    return map;
  }, [rows]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Past and simulated journeys</h1>
        <p className="text-sm text-slate-500">Filter by state: completed, cancelled, replanned, refunded.</p>
      </div>

      {/* Functional status tabs */}
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Trip status filter">
        {TABS.map((tab) => {
          const active = activeTab === tab;
          return (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium transition-colors",
                active
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
              )}
            >
              {tab}
              <span className={cn("rounded-full px-1.5 text-xs", active ? "bg-white/20" : "bg-slate-100 text-slate-500")}>
                {counts[tab]}
              </span>
            </button>
          );
        })}
      </div>

      {visibleRows.length ? (
        <div className="grid gap-4">
          {visibleRows.map((row) => (
            <Card key={`${row.trip}-${row.label}`}>
              <CardHeader><CardTitle>{row.label}</CardTitle></CardHeader>
              <CardContent className="flex flex-wrap items-center justify-between gap-3 text-sm">
                <span>{row.trip}</span>
                <Badge tone={row.status === "cancelled" ? "red" : row.status.includes("confirm") ? "green" : "amber"}>{row.status}</Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          title={activeTab === "All" ? "No history yet" : `No ${activeTab.toLowerCase()} trips`}
          message={
            activeTab === "All"
              ? "Confirmed bookings and demo disruptions will appear here during this browser session."
              : "Switch tabs or take an action (book, cancel, or replan) to populate this view."
          }
        />
      )}
      {plan ? <Link className="text-sm font-medium" href={`/journey/${plan.trip_id}`}>Open current trip</Link> : null}
    </div>
  );
}
