import { Clock3, IndianRupee, MapPinned } from "lucide-react";
import type { ItineraryOption } from "@/models/journey";
import { formatInr, formatMinutes, pct } from "@/lib/utils";

export function JourneyMetrics({ itinerary }: { itinerary: ItineraryOption }) {
  const arrival = itinerary.legs[itinerary.legs.length - 1]?.arrival;
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Metric icon={<IndianRupee className="h-4 w-4" />} label="Total" value={formatInr(itinerary.total_price)} />
      <Metric icon={<Clock3 className="h-4 w-4" />} label="Duration" value={formatMinutes(itinerary.total_duration_minutes)} />
      <Metric icon={<MapPinned className="h-4 w-4" />} label="Arrival" value={arrival ? new Date(arrival).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "TBD"} />
      <Metric icon={<Clock3 className="h-4 w-4" />} label="Reliability" value={pct(itinerary.score)} />
    </dl>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <dt className="flex items-center gap-2 text-xs text-slate-500">{icon}{label}</dt>
      <dd className="mt-1 text-sm font-semibold text-slate-950">{value}</dd>
    </div>
  );
}
