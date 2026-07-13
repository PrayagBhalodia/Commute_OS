"use client";

import { useState } from "react";
import { AutonomySelector } from "@/components/shared/AutonomySelector";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { useFeedbackController, usePreferencesController } from "@/controllers/journey-controller";
import { useJourneyStore } from "@/store/journey-store";

export default function PreferencesPage() {
  const userId = useJourneyStore((state) => state.userId);
  const plan = useJourneyStore((state) => state.activePlan);
  const selectedId = useJourneyStore((state) => state.selectedItineraryId);
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
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Current profile</CardTitle></CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <p>Fastest vs cheapest: <strong>{prefs.data?.prefer_fastest ? "Fastest" : prefs.data?.prefer_cheapest ? "Cheapest" : "Balanced"}</strong></p>
            <p>Preferred modes: {(prefs.data?.preferred_modes ?? []).join(", ") || "cab, flight, metro"}</p>
            <p>Avoided modes: {(prefs.data?.avoid_modes ?? []).join(", ") || "None"}</p>
            <p>Comfort preference: {prefs.data?.prefer_comfort ? "High" : "Standard"}</p>
            <p>Sustainability: {prefs.data?.prefer_low_emission ? "Prioritized" : "Balanced"}</p>
            <p>Luggage habits: {prefs.data?.luggage_default ?? 0} default bags</p>
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
              onClick={() => feedback.mutate({ user_id: userId, trip_id: plan?.trip_id, selected_itinerary_id: selectedId, rating: 5, liked: true, preferred_mode: preferred || null, avoid_mode: avoid || null, comment, metadata: { autonomy_level: autonomy } })}
            >
              Save learning signal
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
