"use client";

import { motion } from "framer-motion";
import type { ItineraryOption } from "@/models/journey";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceBadge, RiskBadge } from "./Badges";
import { JourneyMetrics } from "./JourneyMetrics";

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
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card className={selected ? "border-slate-900" : ""}>
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
