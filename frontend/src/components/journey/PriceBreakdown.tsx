import type { ItineraryOption } from "@/models/journey";
import { formatInr } from "@/lib/utils";

export function PriceBreakdown({ itinerary }: { itinerary: ItineraryOption }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-sm font-semibold">Price breakdown</p>
      <div className="mt-3 space-y-2">
        {itinerary.legs.map((leg) => (
          <div key={leg.leg_id} className="flex justify-between gap-3 text-sm">
            <span className="capitalize text-slate-600">{leg.mode} · {leg.operator}</span>
            <span className="font-medium">{formatInr(leg.price)}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex justify-between border-t border-slate-100 pt-3 font-semibold">
        <span>Total</span>
        <span>{formatInr(itinerary.total_price)}</span>
      </div>
    </div>
  );
}
