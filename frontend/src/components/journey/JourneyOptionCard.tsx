"use client";

import { motion } from "framer-motion";
import type { ItineraryOption } from "@/models/journey";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { JourneyMetrics } from "./JourneyMetrics";
import { RouteMap } from "./RouteMap";

export function JourneyOptionCard({
  itinerary,
  selected,
  label,
  onSelect,
}: {
  itinerary: ItineraryOption;
  selected?: boolean;
  label?: string;
  onSelect?: () => void;
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card className={selected ? "border-slate-900" : ""}>
        <CardHeader>
          <CardTitle>{label ?? itinerary.metadata.strategy?.toString().replace("_", " ") ?? "Journey option"}</CardTitle>
          <p className="mt-1 text-sm text-slate-600">{itinerary.explanation}</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <JourneyMetrics itinerary={itinerary} />
          {selected ? (
            <div className="space-y-1">
              <RouteMap itinerary={itinerary} />
              <p className="text-[11px] text-slate-400">
                Scroll to zoom · road legs follow real roads, flights shown as arcs.
              </p>
            </div>
          ) : null}
          {onSelect ? (
            <Button type="button" variant={selected ? "primary" : "secondary"} onClick={onSelect}>
              {selected ? "Selected" : "Select itinerary"}
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </motion.div>
  );
}
