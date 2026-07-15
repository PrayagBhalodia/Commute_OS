"use client";

import { useState } from "react";
import {
  Armchair,
  Ban,
  Clock,
  Dna,
  History,
  IndianRupee,
  Loader2,
  Luggage,
  MapPin,
  Sparkles,
  Star,
  ThumbsDown,
  ThumbsUp,
  TrendingUp,
  Wallet,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { AutonomySelector } from "@/components/shared/AutonomySelector";
import { JourneyStyleSelector } from "@/components/shared/JourneyStyleSelector";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { useFeedbackController, usePreferencesController } from "@/controllers/journey-controller";
import { PRIORITY_LABELS } from "@/lib/priority";
import { cn, formatInr } from "@/lib/utils";
import { useJourneyStore } from "@/store/journey-store";

const MODES = ["cab", "auto", "metro", "bus", "train", "flight"] as const;

export default function PreferencesPage() {
  const userId = useJourneyStore((state) => state.userId);
  const plan = useJourneyStore((state) => state.activePlan);
  const selectedId = useJourneyStore((state) => state.selectedItineraryId);
  const priority = useJourneyStore((state) => state.priority);
  const prefs = usePreferencesController(userId);
  const feedback = useFeedbackController();

  const [autonomy, setAutonomy] = useState("manual");
  const [rating, setRating] = useState(0);
  const [liked, setLiked] = useState<boolean | null>(null);
  const [preferred, setPreferred] = useState("");
  const [avoid, setAvoid] = useState("");
  const [comment, setComment] = useState("");

  const data = prefs.data;
  const interactionCount = data?.interaction_count ?? 0;
  const preferredModes = data?.preferred_modes ?? [];
  const avoidModes = data?.avoid_modes ?? [];
  const signals = (data?.notes ?? []).slice().reverse();
  const updatedAt = data?.updated_at ? formatTimestamp(data.updated_at) : null;

  const lenses = [
    { label: "Time", icon: Zap, active: Boolean(data?.prefer_fastest) },
    { label: "Cost", icon: IndianRupee, active: Boolean(data?.prefer_cheapest) },
    { label: "Comfort", icon: Armchair, active: Boolean(data?.prefer_comfort) },
  ];

  const canSubmit =
    rating > 0 || liked !== null || Boolean(preferred) || Boolean(avoid) || comment.trim().length > 0;

  function submitFeedback() {
    feedback.mutate(
      {
        user_id: userId,
        trip_id: plan?.trip_id,
        selected_itinerary_id: selectedId,
        rating: rating || null,
        liked,
        preferred_mode: preferred || null,
        avoid_mode: avoid || null,
        comment: comment.trim() || null,
        metadata: { autonomy_level: autonomy, journey_style: priority },
      },
      {
        onSuccess: () => {
          setRating(0);
          setLiked(null);
          setPreferred("");
          setAvoid("");
          setComment("");
        },
      },
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2.5 text-2xl font-semibold">
            <span className="flex h-9 w-9 items-center justify-center rounded-md bg-brand-600 text-white shadow-brand">
              <Dna className="h-5 w-5" />
            </span>
            Travel DNA
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Your evolving traveller profile — learned from every trip you plan and rate. Autonomy defaults to Manual.
          </p>
        </div>
        <DnaStrength count={interactionCount} />
      </div>

      {prefs.isLoading ? (
        <Card>
          <CardContent className="flex items-center gap-2 py-8 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Sequencing your Travel DNA…
          </CardContent>
        </Card>
      ) : null}

      {/* DNA fingerprint — the learned profile at a glance. */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand-600" /> Your DNA fingerprint
          </CardTitle>
          <p className="mt-1 text-sm text-slate-500">
            Everything below is learned from your choices and feedback — nothing is hard-coded.
          </p>
        </CardHeader>
        <CardContent className="grid gap-6 lg:grid-cols-2">
          {/* Optimisation lens */}
          <div className="space-y-4">
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">Learned optimisation lens</p>
              <div className="grid grid-cols-3 gap-2">
                {lenses.map((lens) => {
                  const Icon = lens.icon;
                  return (
                    <div
                      key={lens.label}
                      className={cn(
                        "flex flex-col items-center gap-1 rounded-lg border p-3 text-center transition",
                        lens.active
                          ? "border-brand-500 bg-brand-50 text-brand-700"
                          : "border-slate-200 bg-slate-50 text-slate-400",
                      )}
                    >
                      <Icon className="h-4 w-4" />
                      <span className="text-xs font-semibold">{lens.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">Adjust optimisation</p>
              <JourneyStyleSelector variant="segmented" />
              <p className="mt-2 text-xs text-slate-400">
                Currently optimising for <strong className="text-slate-600">{PRIORITY_LABELS[priority]}</strong>. Rate a trip
                below to lock this into your DNA.
              </p>
            </div>
          </div>

          {/* Mode affinity + traits */}
          <div className="space-y-4">
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">Preferred modes</p>
              {preferredModes.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {preferredModes.map((mode, index) => (
                    <span
                      key={mode}
                      className={cn(
                        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium capitalize",
                        index === 0
                          ? "border-brand-600 bg-brand-600 text-white"
                          : "border-brand-200 bg-brand-50 text-brand-700",
                      )}
                    >
                      {index === 0 ? <Star className="h-3 w-3 fill-current" /> : null}
                      {mode}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-400">No mode preferences learned yet.</p>
              )}
            </div>
            {avoidModes.length ? (
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">Avoids</p>
                <div className="flex flex-wrap gap-1.5">
                  {avoidModes.map((mode) => (
                    <span
                      key={mode}
                      className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium capitalize text-slate-500 line-through"
                    >
                      <Ban className="h-3 w-3 no-underline" />
                      {mode}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="grid grid-cols-2 gap-2">
              <StatTile icon={Clock} label="Airport buffer" value={`${data?.default_buffer_minutes ?? 45} min`} />
              <StatTile icon={Luggage} label="Default luggage" value={`${data?.luggage_default ?? 0} bag${(data?.luggage_default ?? 0) === 1 ? "" : "s"}`} />
              <StatTile icon={Wallet} label="Budget cap" value={data?.max_budget_inr ? formatInr(data.max_budget_inr) : "No cap"} />
              <StatTile icon={MapPin} label="Home base" value={data?.home_label || "Not set"} />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Train your DNA — real feedback signals. */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-brand-600" /> Train your DNA
            </CardTitle>
            <p className="mt-1 text-sm text-slate-500">Every signal reshapes how future journeys are planned.</p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="mb-1.5 text-sm font-medium text-slate-700">How was your last journey?</p>
              <div className="flex items-center gap-3">
                <StarRating value={rating} onChange={setRating} />
                <div className="ml-auto flex items-center gap-1">
                  <button
                    type="button"
                    aria-pressed={liked === true}
                    onClick={() => setLiked(liked === true ? null : true)}
                    className={cn(
                      "focus-ring flex h-9 w-9 items-center justify-center rounded-md border transition",
                      liked === true ? "border-brand-600 bg-brand-600 text-white" : "border-slate-200 bg-white text-slate-500 hover:border-brand-300",
                    )}
                  >
                    <ThumbsUp className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    aria-pressed={liked === false}
                    onClick={() => setLiked(liked === false ? null : false)}
                    className={cn(
                      "focus-ring flex h-9 w-9 items-center justify-center rounded-md border transition",
                      liked === false ? "border-red-500 bg-red-500 text-white" : "border-slate-200 bg-white text-slate-500 hover:border-red-300",
                    )}
                  >
                    <ThumbsDown className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>

            <div>
              <p className="mb-1.5 text-sm font-medium text-slate-700">Preferred mode</p>
              <div className="flex flex-wrap gap-1.5">
                {MODES.map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    disabled={avoid === mode}
                    onClick={() => setPreferred(preferred === mode ? "" : mode)}
                    className={cn(
                      "focus-ring rounded-full border px-3 py-1 text-xs font-medium capitalize transition disabled:opacity-40",
                      preferred === mode
                        ? "border-brand-600 bg-brand-600 text-white"
                        : "border-slate-200 bg-white text-slate-600 hover:border-brand-300",
                    )}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-1.5 text-sm font-medium text-slate-700">Mode to avoid</p>
              <div className="flex flex-wrap gap-1.5">
                {MODES.map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    disabled={preferred === mode}
                    onClick={() => setAvoid(avoid === mode ? "" : mode)}
                    className={cn(
                      "focus-ring rounded-full border px-3 py-1 text-xs font-medium capitalize transition disabled:opacity-40",
                      avoid === mode
                        ? "border-red-500 bg-red-500 text-white"
                        : "border-slate-200 bg-white text-slate-600 hover:border-red-300",
                    )}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>

            <label className="block">
              <span className="text-sm font-medium text-slate-700">Anything else?</span>
              <Textarea
                className="mt-2 min-h-20"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                placeholder="e.g. I want the cheapest option and I hate long airport transfers."
              />
            </label>

            <Button className="w-full" disabled={!canSubmit || feedback.isPending} onClick={submitFeedback}>
              {feedback.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Save learning signal
            </Button>
          </CardContent>
        </Card>

        {/* Learning history — proves the DNA actually persists and evolves. */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <History className="h-4 w-4 text-brand-600" /> Recent learning signals
            </CardTitle>
            {updatedAt ? <p className="mt-1 text-sm text-slate-500">Last updated {updatedAt}</p> : null}
          </CardHeader>
          <CardContent>
            {signals.length ? (
              <ol className="space-y-3">
                {signals.slice(0, 8).map((note, index) => (
                  <li key={`${note}-${index}`} className="flex gap-3 text-sm">
                    <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-brand-400" />
                    <span className="text-slate-600">{note}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="py-6 text-center text-sm text-slate-400">
                No signals captured yet. Plan a trip and share feedback to start training your DNA.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Autonomy level</CardTitle>
          <p className="mt-1 text-sm text-slate-500">How much the agent may act on your behalf. Sent with every learning signal.</p>
        </CardHeader>
        <CardContent>
          <AutonomySelector value={autonomy} onChange={setAutonomy} />
        </CardContent>
      </Card>
    </div>
  );
}

function StarRating({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <div className="flex items-center gap-0.5" role="radiogroup" aria-label="Journey rating">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} star${n > 1 ? "s" : ""}`}
          onClick={() => onChange(n === value ? 0 : n)}
          className="focus-ring rounded p-0.5 transition hover:scale-110"
        >
          <Star className={cn("h-6 w-6", n <= value ? "fill-brand-500 text-brand-500" : "text-slate-300")} />
        </button>
      ))}
    </div>
  );
}

function StatTile({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
      <p className="flex items-center gap-1.5 text-xs text-slate-500">
        <Icon className="h-3.5 w-3.5" /> {label}
      </p>
      <p className="mt-1 truncate text-sm font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function DnaStrength({ count }: { count: number }) {
  const tier =
    count >= 13 ? "Refined" : count >= 6 ? "Established" : count >= 3 ? "Emerging" : count >= 1 ? "Nascent" : "Forming";
  const pct = Math.min(100, Math.round((count / 15) * 100));
  return (
    <div className="min-w-56 rounded-lg border border-brand-100 bg-white/70 px-4 py-3 shadow-soft">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1 font-medium text-brand-700">
          <TrendingUp className="h-3.5 w-3.5" /> DNA strength
        </span>
        <span className="font-semibold text-slate-700">{tier}</span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-brand-100">
        <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${Math.max(6, pct)}%` }} />
      </div>
      <p className="mt-1.5 text-xs text-slate-500">
        {count} learning {count === 1 ? "signal" : "signals"} captured
      </p>
    </div>
  );
}

function formatTimestamp(value: string): string | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
