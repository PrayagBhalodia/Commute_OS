import { format } from "date-fns";
import type { LegOption } from "@/models/journey";
import { Card } from "@/components/ui/card";
import { formatInr, formatMinutes } from "@/lib/utils";
import { TransportModeIcon } from "./Badges";

export function JourneyLegCard({ leg, status }: { leg: LegOption; status?: string }) {
  const duration = (new Date(leg.arrival).getTime() - new Date(leg.departure).getTime()) / 60000;
  return (
    <Card className="p-4 shadow-none">
      <div className="flex items-start justify-between gap-3">
        <div className="flex gap-3">
          <div className="mt-1 flex h-9 w-9 items-center justify-center rounded-md bg-slate-100 text-slate-700">
            <TransportModeIcon mode={leg.mode} />
          </div>
          <div>
            <p className="text-sm font-semibold capitalize text-slate-950">{leg.mode} · {leg.operator}</p>
            <p className="text-sm text-slate-600">{leg.origin} to {leg.destination}</p>
            <p className="mt-1 text-xs text-slate-500">
              {format(new Date(leg.departure), "MMM d, HH:mm")} to {format(new Date(leg.arrival), "HH:mm")} · {formatMinutes(duration)}
            </p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-sm font-semibold">{formatInr(leg.price)}</p>
          <p className="text-xs text-slate-500">{status ?? "Ready"}</p>
        </div>
      </div>
    </Card>
  );
}
