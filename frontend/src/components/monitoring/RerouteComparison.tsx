import type { DisruptionResponse } from "@/models/disruption";
import { JourneyTimeline } from "@/components/journey/JourneyTimeline";
import { formatInr, formatMinutes } from "@/lib/utils";

export function RerouteComparison({ disruption }: { disruption?: DisruptionResponse }) {
  if (!disruption?.revised_itinerary) return null;
  const itinerary = disruption.revised_itinerary;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-semibold">Alternative route</p>
          <p className="text-sm text-slate-500">New ETA and cost after cancellation and rebooking.</p>
        </div>
        <div className="text-right text-sm">
          <p className="font-semibold">{formatInr(itinerary.total_price)}</p>
          <p className="text-slate-500">{formatMinutes(itinerary.total_duration_minutes)}</p>
        </div>
      </div>
      <div className="mt-4">
        <JourneyTimeline itinerary={itinerary} booking={disruption.rebooking} />
      </div>
      {disruption.reconciliation ? <p className="mt-4 text-sm text-slate-600">{disruption.reconciliation.message}</p> : null}
    </div>
  );
}
