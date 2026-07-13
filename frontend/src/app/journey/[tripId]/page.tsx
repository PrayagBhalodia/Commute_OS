"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Map } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/Status";
import { JourneyMetrics } from "@/components/journey/JourneyMetrics";
import { JourneyTimeline } from "@/components/journey/JourneyTimeline";
import { getSelectedItinerary, useJourneyStore } from "@/store/journey-store";

export default function JourneyDetailPage() {
  const params = useParams<{ tripId: string }>();
  const plan = useJourneyStore((state) => state.activePlan);
  const selectedId = useJourneyStore((state) => state.selectedItineraryId);
  const booking = useJourneyStore((state) => state.booking?.booking);
  const itinerary = getSelectedItinerary(plan, selectedId);

  if (!plan || plan.trip_id !== params.tripId || !itinerary) {
    return <EmptyState title="Trip not available in this browser session" message="Plan a journey first. Prototype plans are stored in the running backend and mirrored locally after planning." />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Journey details</h1>
          <p className="text-sm text-slate-500">{plan.trip_id} · {itinerary.itinerary_id}</p>
        </div>
        <Link href={`/booking/${plan.trip_id}`} className="inline-flex h-10 items-center rounded-md bg-slate-900 px-4 text-sm font-medium text-white">Review booking</Link>
      </div>
      <JourneyMetrics itinerary={itinerary} />
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Card>
          <CardHeader><CardTitle>Transport timeline</CardTitle></CardHeader>
          <CardContent><JourneyTimeline itinerary={itinerary} booking={booking} /></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Map className="h-4 w-4" /> Places</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="rounded-md bg-slate-50 p-3">
              <p className="font-medium">{plan.origin.name}</p>
              <p className="text-slate-500">{plan.origin.lat.toFixed(4)}, {plan.origin.lng.toFixed(4)}</p>
            </div>
            <div className="rounded-md bg-slate-50 p-3">
              <p className="font-medium">{plan.destination.name}</p>
              <p className="text-slate-500">{plan.destination.lat.toFixed(4)}, {plan.destination.lng.toFixed(4)}</p>
            </div>
            <p className="text-slate-500">Map rendering is represented as coordinate placeholders in this prototype UI.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
