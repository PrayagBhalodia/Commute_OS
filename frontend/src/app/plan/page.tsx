"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { ArrowRight, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared/Status";
import { ExecutionTrace } from "@/components/journey/ExecutionTrace";
import { JourneyOptionCard } from "@/components/journey/JourneyOptionCard";
import { DEFAULT_PLAN_FORM } from "@/constants/demo";
import { useJourneyController } from "@/controllers/journey-controller";
import { planRequestSchema } from "@/models/journey";
import type { PlanRequest } from "@/models/journey";
import { getSelectedItinerary, useJourneyStore } from "@/store/journey-store";

export default function PlanPage() {
  const { planMutation } = useJourneyController();
  const plan = useJourneyStore((state) => state.activePlan);
  const selectedId = useJourneyStore((state) => state.selectedItineraryId);
  const selectItinerary = useJourneyStore((state) => state.selectItinerary);
  const trace = useJourneyStore((state) => state.trace);
  const goalText = useJourneyStore((state) => state.goalText);
  const selected = getSelectedItinerary(plan, selectedId);
  const form = useForm<PlanRequest>({
    defaultValues: { ...DEFAULT_PLAN_FORM, goal_text: goalText },
  });

  // Carry the prompt entered on the home page (or the last planned goal) into
  // this page's composer so the user sees the same sentence they submitted.
  useEffect(() => {
    if (goalText) form.setValue("goal_text", goalText);
  }, [goalText, form]);

  const submit = form.handleSubmit((values) => {
    const parsed = planRequestSchema.safeParse(values);
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? "Please describe your journey.");
      return;
    }
    planMutation.mutate({ ...parsed.data, metadata: { priority: "time_reliability" } });
  });

  return (
    <div className="grid gap-6 lg:grid-cols-[420px_1fr]">
      <section>
        <Card>
          <CardHeader><CardTitle>Plan a complete journey</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-4">
              <label className="block text-sm font-medium">Where do you need to be?
                <Textarea className="mt-2" {...form.register("goal_text")} />
              </label>
              <label className="block text-sm font-medium">Date/deadline<Input className="mt-2" type="datetime-local" {...form.register("appointment_time")} /></label>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="block text-sm font-medium">Passengers<Input className="mt-2" type="number" min={1} defaultValue={1} /></label>
                <label className="block text-sm font-medium">Luggage<Input className="mt-2" type="number" min={0} {...form.register("luggage_count", { valueAsNumber: true })} /></label>
                <label className="block text-sm font-medium">Max options<Input className="mt-2" type="number" min={1} max={5} {...form.register("max_options", { valueAsNumber: true })} /></label>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" {...form.register("return_required")} />
                Return journey
              </label>
              <label className="block text-sm font-medium">Required buffer minutes<Input className="mt-2" type="number" min={0} {...form.register("required_buffer_minutes", { valueAsNumber: true })} /></label>
              <div className="grid grid-cols-3 gap-2 text-xs text-slate-600">
                {["Time", "Cost", "Comfort"].map((item) => <div key={item} className="rounded-md border border-slate-200 bg-slate-50 p-2 text-center">{item}</div>)}
              </div>
              {Object.values(form.formState.errors)[0]?.message ? <ErrorState message={String(Object.values(form.formState.errors)[0]?.message)} /> : null}
              <Button type="submit" disabled={planMutation.isPending} className="w-full">
                {planMutation.isPending ? "Composing options" : "Generate recommendations"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </section>

      <section className="space-y-6">
        {planMutation.isPending ? (
          <div className="space-y-3"><LoadingSkeleton className="h-32" /><LoadingSkeleton className="h-32" /><LoadingSkeleton className="h-32" /></div>
        ) : null}
        {!plan && !planMutation.isPending ? <EmptyState title="No plan yet" message="Generate a plan or load the demo from Home." /> : null}
        {plan ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h1 className="text-2xl font-semibold">{plan.origin.name} to {plan.destination.name}</h1>
                <p className="text-sm text-slate-500">{plan.message}</p>
              </div>
              {selected ? (
                <div className="flex gap-2">
                  <Link href={`/journey/${plan.trip_id}`} className="inline-flex h-10 items-center gap-2 rounded-md border border-slate-200 bg-white px-4 text-sm font-medium">
                    Details <ArrowRight className="h-4 w-4" />
                  </Link>
                  <Link href={`/booking/${plan.trip_id}`} className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-medium text-white">
                    Review booking <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
              ) : null}
            </div>
            <div className="grid gap-4">
              {plan.itineraries.map((itinerary, index) => (
                <JourneyOptionCard
                  key={itinerary.itinerary_id}
                  itinerary={itinerary}
                  selected={selectedId === itinerary.itinerary_id}
                  label={index === 0 ? "Recommended" : index === 1 ? "Fastest or comfort option" : "Cheapest or low-risk option"}
                  onSelect={() => selectItinerary(itinerary.itinerary_id)}
                />
              ))}
            </div>
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><RotateCcw className="h-4 w-4" /> Execution Trace</CardTitle></CardHeader>
              <CardContent><ExecutionTrace steps={trace} /></CardContent>
            </Card>
          </>
        ) : null}
      </section>
    </div>
  );
}
