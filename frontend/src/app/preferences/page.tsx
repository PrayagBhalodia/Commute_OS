"use client";

import { useState } from "react";
import { Armchair, IndianRupee, Zap } from "lucide-react";
import { AutonomySelector } from "@/components/shared/AutonomySelector";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { useFeedbackController, usePreferencesController } from "@/controllers/journey-controller";
import { PRIORITY_LABELS, type TripPriority } from "@/lib/priority";
import { cn } from "@/lib/utils";
import { useJourneyStore } from "@/store/journey-store";

// Journey Style options — the same optimisation lenses offered on the Plan
// page. They share the store's `priority`, so a choice here is reflected there
// and vice-versa.
const JOURNEY_STYLES: {
  key: TripPriority;
  icon: typeof Zap;
  description: string;
  activeClass: string;
}[] = [
  { key: "time", icon: Zap, description: "Prioritise the fastest arrival across every leg.", activeClass: "border-sky-500 bg-sky-50 text-sky-700" },
  { key: "cost", icon: IndianRupee, description: "Favour the most affordable combination of legs.", activeClass: "border-amber-500 bg-amber-50 text-amber-700" },
  { key: "comfort", icon: Armchair, description: "Prefer the smoothest, most comfortable ride.", activeClass: "border-violet-500 bg-violet-50 text-violet-700" },
];

export default function PreferencesPage() {
  const userId = useJourneyStore((state) => state.userId);
  const plan = useJourneyStore((state) => state.activePlan);
  const selectedId = useJourneyStore((state) => state.selectedItineraryId);
  const priority = useJourneyStore((state) => state.priority);
  const setPriority = useJourneyStore((state) => state.setPriority);
  const prefs = usePreferencesController(userId);
  const feedback = useFeedbackController();
  const [autonomy, setAutonomy] = useState("manual");
  const [comment, setComment] = useState("Prioritize reliability and time for interview trips.");
  const [preferred, setPreferred] = useState("flight");
  const [avoid, setAvoid] = useState("");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Travel DNA</h1>
        <p className="text-sm text-slate-500">Preferences are learned through selection and feedback. Autonomy defaults to Manual.</p>
      </div>
      <Card>
        <CardHeader><CardTitle>Autonomy level</CardTitle></CardHeader>
        <CardContent><AutonomySelector value={autonomy} onChange={setAutonomy} /></CardContent>
      </Card>

      {/* Journey Style — synced with the Plan page priority. */}
      <Card>
        <CardHeader>
          <CardTitle>Journey style</CardTitle>
          <p className="mt-1 text-sm text-slate-500">Choose how journeys are optimised. This stays in sync with the Plan page.</p>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-3" role="group" aria-label="Journey style">
            {JOURNEY_STYLES.map((style) => {
              const Icon = style.icon;
              const active = priority === style.key;
              return (
                <button
                  key={style.key}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setPriority(style.key)}
                  className={cn(
                    "flex flex-col items-start gap-2 rounded-lg border p-4 text-left transition",
                    active ? style.activeClass : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100",
                  )}
                >
                  <span className="flex items-center gap-2 text-sm font-semibold">
                    <Icon className="h-4 w-4" />
                    {PRIORITY_LABELS[style.key]}
                  </span>
                  <span className="text-xs leading-relaxed text-slate-500">{style.description}</span>
                </button>
              );
            })}
          </div>
          <p className="mt-3 text-xs text-slate-400">
            Currently optimising for <strong>{PRIORITY_LABELS[priority]}</strong>.
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Current profile</CardTitle></CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <p>Journey style: <strong>{PRIORITY_LABELS[priority]}</strong></p>
            <p>Preferred modes: {(prefs.data?.preferred_modes ?? []).join(", ") || "cab, flight, metro"}</p>
            <p>Avoided modes: {(prefs.data?.avoid_modes ?? []).join(", ") || "None"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Submit feedback</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <label className="block text-sm font-medium">Preferred mode<Input className="mt-2" value={preferred} onChange={(event) => setPreferred(event.target.value)} /></label>
            <label className="block text-sm font-medium">Avoid mode<Input className="mt-2" value={avoid} onChange={(event) => setAvoid(event.target.value)} placeholder="Optional" /></label>
            <label className="block text-sm font-medium">Comment<Textarea className="mt-2" value={comment} onChange={(event) => setComment(event.target.value)} /></label>
            <Button
              disabled={feedback.isPending}
              onClick={() => feedback.mutate({ user_id: userId, trip_id: plan?.trip_id, selected_itinerary_id: selectedId, rating: 5, liked: true, preferred_mode: preferred || null, avoid_mode: avoid || null, comment, metadata: { autonomy_level: autonomy, journey_style: priority } })}
            >
              Save learning signal
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
