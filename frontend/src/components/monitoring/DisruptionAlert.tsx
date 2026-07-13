import type { DisruptionResponse } from "@/models/disruption";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatInr } from "@/lib/utils";

export function DisruptionAlert({ disruption }: { disruption?: DisruptionResponse }) {
  if (!disruption) return null;
  return (
    <Card className="border-amber-200">
      <CardHeader>
        <CardTitle>Disruption handled</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>{disruption.message}</p>
        <p className="text-slate-600">Cancelled leg: {disruption.disrupted_leg_id ?? "Auto-selected"}</p>
        <p className="text-slate-600">Refund issued: {formatInr(disruption.refund_total)}</p>
      </CardContent>
    </Card>
  );
}
