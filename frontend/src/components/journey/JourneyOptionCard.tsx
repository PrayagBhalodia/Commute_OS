"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { MapPin } from "lucide-react";
import type { ItineraryOption } from "@/models/journey";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceBadge, RiskBadge } from "./Badges";
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
  const breakdown = itinerary.metadata.score_breakdown as Record<string, number> | undefined;
  const [showMap, setShowMap] = useState(false);
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card
        className={selected ? "border-slate-900" : ""}
        onMouseEnter={() => setShowMap(true)}
        onMouseLeave={() => setShowMap(false)}
      >
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>{label ?? itinerary.metadata.strategy?.toString().replace("_", " ") ?? "Journey option"}</CardTitle>
              <p className="mt-1 text-sm text-slate-600">{itinerary.explanation}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <ConfidenceBadge score={itinerary.score} />
              <RiskBadge score={itinerary.score} emission={itinerary.total_emission_kg} />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <JourneyMetrics itinerary={itinerary} />
          <div className="space-y-1">
            {showMap ? (
              <RouteMap itinerary={itinerary} />
            ) : (
              <div className="flex h-48 items-center justify-center gap-2 rounded-md border border-dashed border-slate-200 bg-slate-50 text-xs text-slate-400">
                <MapPin className="h-4 w-4" /> Hover to preview the route on a map
              </div>
            )}
            <p className="text-[11px] text-slate-400">
              {showMap ? "Scroll to zoom · road legs follow real roads, flights shown as arcs." : "Road legs follow real roads; flights are shown as arcs."}
            </p>
          </div>
          <div className="text-xs text-slate-500">
            Ranked by {breakdown ? `time ${Math.round((breakdown.time ?? 0) * 100)}%, cost ${Math.round((breakdown.price ?? 0) * 100)}%, comfort ${Math.round((breakdown.comfort ?? 0) * 100)}%, eco ${Math.round((breakdown.eco ?? 0) * 100)}%` : "preference-weighted score"}.
          </div>
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

export function RecommendedJourneyCard({ itinerary }: { itinerary: ItineraryOption }) {
  return <JourneyOptionCard itinerary={itinerary} selected label="Recommended option" />;
}
