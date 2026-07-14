"use client";

import { useState } from "react";
import { Activity, ArrowRight, Bell, XCircle, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/Status";
import { CancelReasonDialog } from "@/components/journey/CancelReasonDialog";
import { JourneyTimeline } from "@/components/journey/JourneyTimeline";
import { DisruptionAlert } from "@/components/monitoring/DisruptionAlert";
import { RerouteComparison } from "@/components/monitoring/RerouteComparison";
import { useDisruptionController } from "@/controllers/disruption-controller";
import { useBookingStatusSync, useCancelBookingController } from "@/controllers/booking-controller";
import { formatInr } from "@/lib/utils";
import {
  journeyEndpoints,
  journeySegments,
  segmentProgress,
  SEGMENT_PROGRESS_LABEL,
  type SegmentProgress,
} from "@/lib/segments";
import { getSelectedItinerary, useJourneyStore } from "@/store/journey-store";

const PROGRESS_TONE: Record<SegmentProgress, "green" | "amber" | "neutral"> = {
  finished: "green",
  ongoing: "amber",
  upcoming: "neutral",
};

export default function ActivePage() {
  const userId = useJourneyStore((state) => state.userId);
  const plan = useJourneyStore((state) => state.activePlan);
  const selectedId = useJourneyStore((state) => state.selectedItineraryId);
  const booking = useJourneyStore((state) => state.booking?.booking);
  const disruption = useJourneyStore((state) => state.disruption);
  const itinerary = getSelectedItinerary(plan, selectedId);
  const disrupt = useDisruptionController();
  const cancel = useCancelBookingController(userId);
  const [confirmingTrip, setConfirmingTrip] = useState(false);
  // Server-driven sync: refetch the booking on mount so a reload reflects
  // the authoritative status (e.g. a trip cancelled in another session).
  useBookingStatusSync(booking?.trip_id);

  if (!plan || !itinerary || !booking) {
    return <EmptyState title="No active booked journey" message="Plan and confirm the demo journey first, then return here to trigger a disruption." />;
  }

  // Cancelled trips are history, not active journeys.
  if (booking.status === "cancelled") {
    return <EmptyState title="No active journey" message="Your last trip was cancelled and refunded. Find it in the History tab." />;
  }

  const currentLeg = itinerary.legs[0];
  const nextLeg = itinerary.legs[1];
  const { initial, final } = journeyEndpoints(itinerary);
  const segments = journeySegments(itinerary);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <section className="space-y-6">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold"><Activity className="h-6 w-6" /> Active journey</h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-lg font-medium text-slate-900">
            <span>{initial}</span>
            <ArrowRight className="h-4 w-4 text-slate-400" />
            <span>{final}</span>
            <Badge tone="amber">Ongoing</Badge>
          </p>
          <p className="text-sm text-slate-500">Trip {plan.trip_id} · ETA {new Date(itinerary.legs[itinerary.legs.length - 1].arrival).toLocaleString()}</p>
        </div>
        <Card>
          <CardHeader><CardTitle>Journey segments</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {segments.map((segment, index) => {
              const progress = segmentProgress(index, segments.length);
              return (
                <div
                  key={segment.leg_id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
                >
                  <span className="flex flex-wrap items-center gap-2 font-medium text-slate-900">
                    <span>{segment.from}</span>
                    <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                    <span>{segment.to}</span>
                  </span>
                  <Badge tone={PROGRESS_TONE[progress]}>{SEGMENT_PROGRESS_LABEL[progress]}</Badge>
                </div>
              );
            })}
          </CardContent>
        </Card>
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
        <Card>
          <CardHeader><CardTitle>Manage booking</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            {booking.leg_confirmations.map((leg) => {
              const cancellable = leg.status === "confirmed";
              return (
                <div key={leg.leg_id} className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium capitalize">{leg.mode} · {leg.operator}</p>
                    <p className="capitalize text-slate-500">{leg.status} · {formatInr(leg.price_charged)}</p>
                  </div>
                  <Button
                    variant="ghost"
                    className="h-8 shrink-0 px-3 text-red-700 hover:bg-red-50"
                    disabled={!cancellable || cancel.cancelLeg.isPending}
                    onClick={() => cancel.cancelLeg.mutate({ tripId: booking.trip_id, legId: leg.leg_id })}
                  >
                    {cancellable ? "Cancel" : leg.status}
                  </Button>
                </div>
              );
            })}
            <div className="border-t border-slate-100 pt-3">
              {confirmingTrip ? (
                <CancelReasonDialog
                  loading={cancel.cancelTrip.isPending}
                  onDismiss={() => setConfirmingTrip(false)}
                  onConfirm={({ category, note }) =>
                    cancel.cancelTrip.mutate(
                      {
                        tripId: booking.trip_id,
                        reason: { reason_category: category, reason_note: note ?? null },
                      },
                      { onSuccess: () => setConfirmingTrip(false) },
                    )
                  }
                />
              ) : (
                <Button
                  variant="danger"
                  className="w-full"
                  disabled={!booking.leg_confirmations.some((leg) => leg.status === "confirmed")}
                  onClick={() => setConfirmingTrip(true)}
                >
                  <XCircle className="h-4 w-4" /> Cancel entire trip
                </Button>
              )}
            </div>
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
