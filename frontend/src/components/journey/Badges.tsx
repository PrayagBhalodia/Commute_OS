import { Bus, Car, Plane, Train, TramFront } from "lucide-react";
import type { TransportMode } from "@/models/journey";

export function TransportModeIcon({ mode }: { mode: TransportMode }) {
  const className = "h-4 w-4";
  if (mode === "flight") return <Plane className={className} />;
  if (mode === "train") return <Train className={className} />;
  if (mode === "bus") return <Bus className={className} />;
  if (mode === "metro") return <TramFront className={className} />;
  return <Car className={className} />;
}
