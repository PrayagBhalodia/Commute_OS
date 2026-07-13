"use client";

import { Activity, Bell, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/Status";
import { JourneyTimeline } from "@/components/journey/JourneyTimeline";
import { DisruptionAlert } from "@/components/monitoring/DisruptionAlert";
import { RerouteComparison } from "@/components/monitoring/RerouteComparison";
import { useDisruptionController } from "@/controllers/disruption-controller";
import { getSelectedItinerary, useJourneyStore } from "@/store/journey-store";

export default function ActivePage() {
  const userId = useJourneyStore((state) => state.userId);
  const plan = useJourneyStore((state) => state.activePlan);
  const selectedId = useJourneyStore((state) => state.selectedItineraryId);
  const booking = useJourneyStore((state) => state.booking?.booking);
  const disruption = useJourneyStore((state) => state.disruption);
  const itinerary = getSelectedItinerary(plan, selectedId);
  const disrupt = useDisruptionController();

  if (!plan || !itinerary || !booking) {
    return <EmptyState title="No active booked journey" message="Plan and confirm the demo journey first, then return here to trigger a disruption." />;
  }

  const currentLeg = itinerary.legs[0];
  const nextLeg = itinerary.legs[1];

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <section className="space-y-6">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold"><Activity className="h-6 w-6" /> Active journey</h1>
          <p className="text-sm text-slate-500">Trip {plan.trip_id} · ETA {new Date(itinerary.legs[itinerary.legs.length - 1].arrival).toLocaleString()}</p>
        </div>
        <Card>
          <CardHeader><CardTitle>Progress timeline</CardTitle></CardHeader>
          <CardContent><JourneyTimeline itinerary={itinerary} booking={booking} /></CardContent>
        </Card>
        <DisruptionAlert disruption={disruption} />
        <RerouteComparison disruption={disruption} />
      </section>
      <aside className="space-y-4">
        <Card>
          <CardHeader><CardTitle>Now</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>Current leg: <strong>{currentLeg.mode} · {currentLeg.operator}</strong></p>
            <p className="text-slate-600">{currentLeg.origin} to {currentLeg.destination}</p>
            <p>Next leg: {nextLeg ? `${nextLeg.mode} · ${nextLeg.operator}` : "Arrive"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Bell className="h-4 w-4" /> Notifications</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm text-slate-600">
            <p>Weather placeholder: clear enough for planned route.</p>
            <p>Traffic placeholder: monitor first and last-mile buffers.</p>
          </CardContent>
        </Card>
        <Button
          variant="danger"
          className="w-full"
          disabled={disrupt.isPending}
          onClick={() => disrupt.mutate({ trip_id: plan.trip_id, user_id: userId, reason: "traffic_delay", severity: "medium", auto_rebook: true })}
        >
          <Zap className="h-4 w-4" /> {disrupt.isPending ? "Handling disruption" : "Trigger demo disruption"}
        </Button>
      </aside>
    </div>
  );
}
