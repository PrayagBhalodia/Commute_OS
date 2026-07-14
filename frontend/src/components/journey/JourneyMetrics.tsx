import { Armchair, Clock3, IndianRupee, Leaf, MapPinned } from "lucide-react";
import type { ItineraryOption } from "@/models/journey";
import { formatInr, formatMinutes } from "@/lib/utils";
import { avgComfort, ecoLabel } from "@/lib/priority";

export function JourneyMetrics({ itinerary }: { itinerary: ItineraryOption }) {
  const arrival = itinerary.legs[itinerary.legs.length - 1]?.arrival;
  const comfort = Math.round(avgComfort(itinerary) * 100);
  const eco = ecoLabel(itinerary);
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <Metric icon={<IndianRupee className="h-4 w-4" />} label="Total" value={formatInr(itinerary.total_price)} />
      <Metric icon={<Clock3 className="h-4 w-4" />} label="Duration" value={formatMinutes(itinerary.total_duration_minutes)} />
      <Metric icon={<MapPinned className="h-4 w-4" />} label="Arrival" value={arrival ? new Date(arrival).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "TBD"} />
      <Metric icon={<Armchair className="h-4 w-4" />} label="Comfort" value={`${comfort}%`} />
      <Metric icon={<Leaf className="h-4 w-4" />} label="Eco" value={eco.text.replace(" footprint", "")} tone={eco.tone} />
    </dl>
  );
}

function Metric({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: "green" | "amber" | "red";
}) {
  const toneClass =
    tone === "green"
      ? "text-emerald-700"
      : tone === "red"
        ? "text-red-700"
        : tone === "amber"
          ? "text-amber-700"
          : "text-slate-950";
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <dt className="flex items-center gap-2 text-xs text-slate-500">{icon}{label}</dt>
      <dd className={`mt-1 text-sm font-semibold ${toneClass}`}>{value}</dd>
    </div>
  );
}
