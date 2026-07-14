"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowRight, ChevronDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/Status";
import { cn } from "@/lib/utils";
import { journeyEndpoints, journeySegments, type JourneySegment } from "@/lib/segments";
import type { ItineraryOption } from "@/models/journey";
import { getSelectedItinerary, useJourneyStore } from "@/store/journey-store";

// The status filters, plus an "All" that shows everything.
const TABS = ["All", "Completed", "Cancelled"] as const;
type Tab = (typeof TABS)[number];

interface TripRow {
  trip: string;
  label: string;
  status: string;
  itinerary?: ItineraryOption;
  // Which filter tabs this trip belongs to.
  categories: Exclude<Tab, "All">[];
}

/** Map a raw booking status into the filter categories it satisfies. */
function bookingCategories(status: string): Exclude<Tab, "All">[] {
  if (status === "cancelled") return ["Cancelled"];
  if (status === "partially_cancelled") return ["Completed", "Cancelled"];
  if (status === "confirmed") return ["Completed"];
  return [];
}

/** Expandable trip card: collapsed shows Initial → Final, expanded lists segments. */
function TripCard({ row }: { row: TripRow }) {
  const [open, setOpen] = useState(false);
  const { initial, final } = journeyEndpoints(row.itinerary);
  const segments: JourneySegment[] = journeySegments(row.itinerary);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>{row.label}</CardTitle>
          <Badge tone={row.status === "cancelled" ? "red" : row.status.includes("confirm") ? "green" : "amber"}>
            {row.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-2 font-medium text-slate-900">
          <span>{initial}</span>
          <ArrowRight className="h-4 w-4 text-slate-400" />
          <span>{final}</span>
        </div>
        {segments.length ? (
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50"
          >
            {open ? "Hide breakdown" : "View full breakdown"}
            <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
          </button>
        ) : null}
        {open ? (
          <ol className="space-y-2 border-l border-slate-200 pl-4">
            {segments.map((segment, index) => (
              <li key={segment.leg_id} className="flex flex-wrap items-center gap-2 text-slate-700">
                <span className="text-xs text-slate-400">Segment {index + 1}</span>
                <span className="font-medium">{segment.from}</span>
                <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                <span className="font-medium">{segment.to}</span>
              </li>
            ))}
          </ol>
        ) : null}
        <div className="pt-1 text-xs text-slate-400">{row.trip}</div>
      </CardContent>
    </Card>
  );
}

export default function HistoryPage() {
  const plan = useJourneyStore((state) => state.activePlan);
  const selectedId = useJourneyStore((state) => state.selectedItineraryId);
  const returnPlan = useJourneyStore((state) => state.returnPlan);
  const selectedReturnId = useJourneyStore((state) => state.selectedReturnItineraryId);
  const booking = useJourneyStore((state) => state.booking?.booking);
  const [activeTab, setActiveTab] = useState<Tab>("All");

  const rows = useMemo<TripRow[]>(() => {
    const list: TripRow[] = [];
    if (booking) {
      list.push({
        trip: booking.trip_id,
        label: booking.status === "cancelled" ? "Cancelled journey" : "Booked journey",
        status: booking.status,
        itinerary: getSelectedItinerary(plan, selectedId),
        categories: bookingCategories(booking.status),
      });
      const returnItinerary = getSelectedItinerary(returnPlan, selectedReturnId);
      if (returnItinerary) {
        list.push({
          trip: `${booking.trip_id} · return`,
          label: "Return journey",
          status: booking.status,
          itinerary: returnItinerary,
          categories: bookingCategories(booking.status),
        });
      }
    }
    return list;
  }, [booking, plan, selectedId, returnPlan, selectedReturnId]);

  const visibleRows = useMemo(
    () => (activeTab === "All" ? rows : rows.filter((row) => row.categories.includes(activeTab))),
    [rows, activeTab],
  );

  // Per-tab counts so the tabs communicate what's behind them.
  const counts = useMemo(() => {
    const map: Record<Tab, number> = { All: rows.length, Completed: 0, Cancelled: 0 };
    for (const row of rows) for (const category of row.categories) map[category] += 1;
    return map;
  }, [rows]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Past and simulated journeys</h1>
        <p className="text-sm text-slate-500">Filter by state and expand any trip to see its full segment breakdown.</p>
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
            <TripCard key={`${row.trip}-${row.label}`} row={row} />
          ))}
        </div>
      ) : (
        <EmptyState
          title={activeTab === "All" ? "No history yet" : `No ${activeTab.toLowerCase()} trips`}
          message={
            activeTab === "All"
              ? "Confirmed bookings will appear here during this browser session."
              : "Switch tabs or book a trip to populate this view."
          }
        />
      )}
      {plan ? <Link className="text-sm font-medium" href={`/journey/${plan.trip_id}`}>Open current trip</Link> : null}
    </div>
  );
}
