"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { ArrowRight, Armchair, IndianRupee, RotateCcw, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared/Status";
import { ExecutionTrace } from "@/components/journey/ExecutionTrace";
import { JourneyOptionCard } from "@/components/journey/JourneyOptionCard";
import { DateTimeModal, type DateTimeModalResult } from "@/components/journey/DateTimeModal";
import { DEFAULT_PLAN_FORM } from "@/constants/demo";
import { useJourneyController } from "@/controllers/journey-controller";
import { planRequestSchema } from "@/models/journey";
import type { PlanRequest } from "@/models/journey";
import { PRIORITY_LABELS, rankByPriority, type TripPriority } from "@/lib/priority";
import { cn } from "@/lib/utils";
import { getSelectedItinerary, useJourneyStore } from "@/store/journey-store";

// Priority lenses shown under the composer. Each maps to a distinct icon and
// accent so the active choice reads clearly against the rest of the UI.
const PRIORITIES: { key: TripPriority; icon: typeof Zap; activeClass: string }[] = [
  { key: "time", icon: Zap, activeClass: "border-sky-500 bg-sky-50 text-sky-700" },
  { key: "cost", icon: IndianRupee, activeClass: "border-amber-500 bg-amber-50 text-amber-700" },
  { key: "comfort", icon: Armchair, activeClass: "border-violet-500 bg-violet-50 text-violet-700" },
];

// Heuristic: does the trip description already mention a date, time, or
// duration? If so we can plan straight away instead of prompting for one.
const DATETIME_HINT =
  /\b(today|tonight|tomorrow|tmrw|day after tomorrow|next\s+(?:week|month|mon|tue|wed|thu|fri|sat|sun)[a-z]*|this\s+(?:evening|afternoon|morning|weekend)|mon|tue|wed|thu|fri|sat|sun)[a-z]*\b|\b\d{1,2}\s*(?:am|pm)\b|\b\d{1,2}:\d{2}\b|\b(?:at|by|before|after|around)\s+\d{1,2}\b|\bin\s+\d+\s*(?:min|mins|minute|minutes|hour|hours|hrs|day|days|week|weeks)\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b|\b\d{1,2}(?:st|nd|rd|th)\b|\b\d{1,2}\/\d{1,2}\b/i;

type ModalMode = "start" | "return";
type ModalIntent = "plan" | "capture";

/** "16/07 at 09:00" from an ISO-ish datetime, or null when unparseable. */
function formatWhen(iso?: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const dd = String(date.getDate()).padStart(2, "0");
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const min = String(date.getMinutes()).padStart(2, "0");
  return `${dd}/${mm} at ${hh}:${min}`;
}

export default function PlanPage() {
  const { planMutation, returnPlanMutation } = useJourneyController();
  const plan = useJourneyStore((state) => state.activePlan);
  const selectedId = useJourneyStore((state) => state.selectedItineraryId);
  const selectItinerary = useJourneyStore((state) => state.selectItinerary);
  const returnPlan = useJourneyStore((state) => state.returnPlan);
  const clearReturnPlan = useJourneyStore((state) => state.clearReturnPlan);
  const trace = useJourneyStore((state) => state.trace);
  const goalText = useJourneyStore((state) => state.goalText);
  const priority = useJourneyStore((state) => state.priority);
  const setPriority = useJourneyStore((state) => state.setPriority);
  const startDateTime = useJourneyStore((state) => state.startDateTime);
  const returnDateTime = useJourneyStore((state) => state.returnDateTime);
  const setSchedule = useJourneyStore((state) => state.setSchedule);
  const selected = getSelectedItinerary(plan, selectedId);

  // One-line journey summary ("From A to B on DD/MM at HH:MM …") shown with
  // the results — the same trip whether it was planned here or in the chat.
  const goalContext = plan?.intent?.goal_context;
  const departWhen = formatWhen(goalContext?.appointment_time ?? startDateTime);
  const returnWhen = formatWhen(returnDateTime);
  const journeySummary = plan
    ? [
        `From ${plan.origin.name} to ${plan.destination.name}`,
        departWhen ? `on ${departWhen}` : null,
        returnWhen ? `returning ${returnWhen}` : null,
        goalContext?.luggage_count
          ? `${goalContext.luggage_count} bag${goalContext.luggage_count > 1 ? "s" : ""}`
          : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : null;

  const form = useForm<PlanRequest>({
    // Return trip is unchecked by default (requirement 3).
    defaultValues: { ...DEFAULT_PLAN_FORM, goal_text: goalText, return_required: false },
  });
  const returnRequired = Boolean(form.watch("return_required"));

  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<ModalMode>("start");
  const [modalIntent, setModalIntent] = useState<ModalIntent>("plan");

  // Carry the prompt entered on the home page (or last planned goal) into the
  // composer so the user sees the same sentence they submitted.
  useEffect(() => {
    if (goalText) form.setValue("goal_text", goalText);
  }, [goalText, form]);

  // Re-rank the returned options for the active priority. Pure + instant, so
  // switching priority reorders the cards immediately (eco is client-only).
  const ranked = useMemo(
    () => (plan ? rankByPriority(plan.itineraries, priority) : []),
    [plan, priority],
  );

  // Auto-select the best option for the current priority whenever the priority
  // changes or a fresh plan arrives.
  useEffect(() => {
    if (ranked[0]) selectItinerary(ranked[0].itinerary_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [priority, plan?.trip_id]);

  // Fire the plan request, mapping form + schedule + priority into the payload.
  // When a round trip is requested, chain a second plan for the return leg
  // (origin/destination swapped, scheduled for the return date) so the Review
  // tab can reflect both journeys.
  const doPlan = useCallback(
    (overrides?: Partial<PlanRequest>, priorityArg?: TripPriority) => {
      const values = { ...form.getValues(), ...overrides };
      const parsed = planRequestSchema.safeParse(values);
      if (!parsed.success) {
        toast.error(parsed.error.issues[0]?.message ?? "Please describe your journey.");
        return;
      }
      const activePriority = priorityArg ?? priority;
      const metadata: Record<string, unknown> = { priority: activePriority };
      if (returnDateTime) metadata.return_time = returnDateTime;
      const wantsReturn = Boolean(values.return_required) && Boolean(returnDateTime);

      planMutation.mutate(
        { ...parsed.data, metadata },
        {
          onSuccess: (onward) => {
            if (!wantsReturn) {
              clearReturnPlan();
              return;
            }
            // Build a return goal from the resolved endpoints, swapped.
            const returnGoal = `Return trip from ${onward.destination.name} to ${onward.origin.name} on ${returnDateTime}`;
            returnPlanMutation.mutate({
              user_id: parsed.data.user_id,
              goal_text: returnGoal,
              origin: onward.destination.name,
              destination: onward.origin.name,
              appointment_time: returnDateTime,
              return_required: false,
              max_options: parsed.data.max_options,
              metadata: { priority: activePriority, leg: "return" },
            });
          },
        },
      );
    },
    [form, priority, returnDateTime, planMutation, returnPlanMutation, clearReturnPlan],
  );

  // Plan Trip: if we can't find a start time in the description (and none was
  // captured), open the modal; otherwise plan straight away.
  const submit = form.handleSubmit((values) => {
    const parsed = planRequestSchema.safeParse(values);
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? "Please describe your journey.");
      return;
    }
    const hasWhen = DATETIME_HINT.test(values.goal_text) || Boolean(startDateTime);
    if (!hasWhen) {
      setModalMode(values.return_required ? "return" : "start");
      setModalIntent("plan");
      setModalOpen(true);
      return;
    }
    doPlan();
  });

  // Return checkbox: opens the same modal (now with return fields) to capture
  // both start + return; unchecking clears the stored return.
  const handleReturnToggle = () => {
    const next = !returnRequired;
    form.setValue("return_required", next);
    if (next) {
      setModalMode("return");
      setModalIntent("capture");
      setModalOpen(true);
    } else {
      setSchedule({ startDateTime, returnDateTime: undefined });
      clearReturnPlan();
    }
  };

  const handleModalConfirm = ({ startDateTime: start, returnDateTime: ret }: DateTimeModalResult) => {
    setSchedule({ startDateTime: start, returnDateTime: ret });
    form.setValue("appointment_time", start);
    if (modalMode === "return") form.setValue("return_required", true);
    setModalOpen(false);
    if (modalIntent === "plan") {
      doPlan({ appointment_time: start, return_required: modalMode === "return" });
    }
  };

  const handleModalCancel = () => {
    setModalOpen(false);
    // If the return modal was dismissed without confirming, leave the box
    // unchecked so we never claim a return without dates.
    if (modalMode === "return" && !returnDateTime) form.setValue("return_required", false);
  };

  // Priority click: switch lens and replan the existing trip against it.
  const handlePriorityChange = (next: TripPriority) => {
    if (next === priority) return;
    setPriority(next);
    if (plan) doPlan(undefined, next);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[420px_1fr]">
      <section>
        <Card>
          <CardHeader><CardTitle>Plan a complete journey</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-4">
              <label className="block text-sm font-medium">Where do you need to be?
                <Textarea
                  className="mt-2"
                  placeholder="e.g. Interview at Jio Institute in Navi Mumbai from Ahmedabad next Tuesday morning"
                  {...form.register("goal_text")}
                />
              </label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm font-medium">Passengers<Input className="mt-2" type="number" min={1} defaultValue={1} /></label>
                <label className="block text-sm font-medium">Max options<Input className="mt-2" type="number" min={2} max={5} {...form.register("max_options", { valueAsNumber: true })} /></label>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={returnRequired}
                  onChange={handleReturnToggle}
                  className="rounded border-slate-300"
                />
                Return journey
              </label>

              {/* Priority selector — switching one triggers a replan. */}
              <div>
                <p className="mb-2 text-sm font-medium text-slate-700">Optimize for</p>
                <div className="grid grid-cols-3 gap-2" role="group" aria-label="Trip priority">
                  {PRIORITIES.map((p) => {
                    const Icon = p.icon;
                    const active = priority === p.key;
                    return (
                      <button
                        key={p.key}
                        type="button"
                        aria-pressed={active}
                        onClick={() => handlePriorityChange(p.key)}
                        className={cn(
                          "flex flex-col items-center gap-1 rounded-md border p-2 text-xs font-medium transition",
                          active ? p.activeClass : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100",
                        )}
                      >
                        <Icon className="h-4 w-4" />
                        {PRIORITY_LABELS[p.key]}
                      </button>
                    );
                  })}
                </div>
              </div>

              {Object.values(form.formState.errors)[0]?.message ? <ErrorState message={String(Object.values(form.formState.errors)[0]?.message)} /> : null}
              <Button type="submit" disabled={planMutation.isPending} className="w-full">
                {planMutation.isPending ? "Composing options" : "Plan trip"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </section>

      <section className="space-y-6">
        {planMutation.isPending ? (
          <div className="space-y-3"><LoadingSkeleton className="h-32" /><LoadingSkeleton className="h-32" /><LoadingSkeleton className="h-32" /></div>
        ) : null}
        {!plan && !planMutation.isPending ? <EmptyState title="No plan yet" message="Describe your trip and plan it, or load the demo from Home." /> : null}
        {plan && ranked.length ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h1 className="text-2xl font-semibold">{plan.origin.name} to {plan.destination.name}</h1>
                {journeySummary ? (
                  <p className="mt-1 text-sm font-medium text-slate-700">{journeySummary}</p>
                ) : null}
                <p className="text-sm text-slate-500">
                  {ranked.length} options · optimized for {PRIORITY_LABELS[priority].toLowerCase()} · {plan.message}
                </p>
                {returnPlan ? (
                  <p className="mt-1 text-sm font-medium text-emerald-700">
                    Return journey planned: {returnPlan.origin.name} to {returnPlan.destination.name}
                    {returnDateTime ? ` · ${new Date(returnDateTime).toLocaleString()}` : null}
                  </p>
                ) : returnPlanMutation.isPending ? (
                  <p className="mt-1 text-sm text-slate-500">Planning return journey…</p>
                ) : null}
              </div>
              {selected ? (
                <div className="flex gap-2">
                  <Link href={`/booking/${plan.trip_id}`} className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-medium text-white">
                    Review booking <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
              ) : null}
            </div>
            <div className="grid gap-4">
              {ranked.map((itinerary, index) => (
                <JourneyOptionCard
                  key={itinerary.itinerary_id}
                  itinerary={itinerary}
                  selected={selectedId === itinerary.itinerary_id}
                  label={index === 0 ? `Best for ${PRIORITY_LABELS[priority]}` : "Alternative option"}
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

      <DateTimeModal
        open={modalOpen}
        withReturn={modalMode === "return"}
        initialStart={startDateTime}
        initialReturn={returnDateTime}
        loading={modalIntent === "plan" && planMutation.isPending}
        onConfirm={handleModalConfirm}
        onCancel={handleModalCancel}
      />
    </div>
  );
}
