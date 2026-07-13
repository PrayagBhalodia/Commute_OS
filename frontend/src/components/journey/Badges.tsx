import { Bus, Car, Leaf, Plane, ShieldCheck, Train, TramFront } from "lucide-react";
import type { TransportMode } from "@/models/journey";
import { Badge } from "@/components/ui/badge";
import { pct } from "@/lib/utils";

export function TransportModeIcon({ mode }: { mode: TransportMode }) {
  const className = "h-4 w-4";
  if (mode === "flight") return <Plane className={className} />;
  if (mode === "train") return <Train className={className} />;
  if (mode === "bus") return <Bus className={className} />;
  if (mode === "metro") return <TramFront className={className} />;
  return <Car className={className} />;
}

export function ConfidenceBadge({ score }: { score: number }) {
  const tone = score > 0.72 ? "green" : score > 0.5 ? "amber" : "red";
  return (
    <Badge tone={tone}>
      <ShieldCheck className="h-3 w-3" /> {pct(score)} confidence
    </Badge>
  );
}

export function RiskBadge({ score, emission }: { score: number; emission?: number | null }) {
  const risk = score > 0.72 ? "Low risk" : score > 0.5 ? "Moderate risk" : "Higher risk";
  return (
    <Badge tone={score > 0.72 ? "green" : "amber"}>
      <Leaf className="h-3 w-3" /> {risk}{emission ? ` · ${Math.round(emission)} kg CO2e` : ""}
    </Badge>
  );
}
