"use client";

import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/Status";
import { useJourneyStore } from "@/store/journey-store";

export default function HistoryPage() {
  const plan = useJourneyStore((state) => state.activePlan);
  const booking = useJourneyStore((state) => state.booking?.booking);
  const disruption = useJourneyStore((state) => state.disruption);
  const rows = [
    booking ? { status: booking.status, trip: booking.trip_id, label: "Booked journey" } : null,
    disruption ? { status: disruption.status, trip: disruption.trip_id, label: "Replanned disruption" } : null,
  ].filter(Boolean) as { status: string; trip: string; label: string }[];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Past and simulated journeys</h1>
        <p className="text-sm text-slate-500">Filter states: completed, cancelled, replanned, refunded.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {["Completed", "Cancelled", "Replanned", "Refunded"].map((filter) => <Badge key={filter}>{filter}</Badge>)}
      </div>
      {rows.length ? (
        <div className="grid gap-4">
          {rows.map((row) => (
            <Card key={`${row.trip}-${row.label}`}>
              <CardHeader><CardTitle>{row.label}</CardTitle></CardHeader>
              <CardContent className="flex flex-wrap items-center justify-between gap-3 text-sm">
                <span>{row.trip}</span>
                <Badge tone={row.status.includes("confirm") ? "green" : "amber"}>{row.status}</Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState title="No history yet" message="Confirmed bookings and demo disruptions will appear here during this browser session." />
      )}
      {plan ? <Link className="text-sm font-medium" href={`/journey/${plan.trip_id}`}>Open current trip</Link> : null}
    </div>
  );
}
