"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Clock, MapPin, WalletCards } from "lucide-react";
import { AssistantComposer } from "@/components/assistant/AssistantComposer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BackendStatus } from "@/components/shared/Status";
import { ASSISTANT_GREETINGS } from "@/constants/demo";
import { useJourneyController, usePreferencesController } from "@/controllers/journey-controller";
import { useWalletController } from "@/controllers/wallet-controller";
import { useHealth } from "@/hooks/use-health";
import { formatInr } from "@/lib/utils";
import { getStoredToken } from "@/services/auth-service";
import { useJourneyStore } from "@/store/journey-store";

export default function HomePage() {
  const [prompt, setPrompt] = useState("");
  const router = useRouter();
  const { planMutation } = useJourneyController();
  const userId = useJourneyStore((state) => state.userId);
  const setGoalText = useJourneyStore((state) => state.setGoalText);
  const plan = useJourneyStore((state) => state.activePlan);
  const { balanceQuery } = useWalletController(userId);
  const prefs = usePreferencesController(userId);
  const health = useHealth();
  const greeting = useMemo(() => ASSISTANT_GREETINGS[new Date().getMinutes() % ASSISTANT_GREETINGS.length], []);
  // Personalised aside cards are only meaningful for a signed-in traveller.
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    setSignedIn(Boolean(getStoredToken()));
  }, []);

  function runPlan(payload: Parameters<typeof planMutation.mutate>[0]) {
    planMutation.mutate(payload, { onSuccess: () => router.push("/plan") });
  }

  // Free-text goal: let the backend's intent agent extract origin/destination
  // from the sentence instead of forcing the hardcoded demo route.
  function submit() {
    if (!getStoredToken()) {
      router.push("/auth?next=/");
      return;
    }
    if (prompt.trim().length < 8) return;
    setGoalText(prompt.trim());
    runPlan({ user_id: userId, goal_text: prompt.trim(), max_options: 3 });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <section className="space-y-6">
        <div className="space-y-3">
          <p className="text-sm font-medium text-teal-700">AI-first Journey Operating System</p>
          <h1 className="max-w-3xl text-4xl font-semibold tracking-normal text-slate-950 sm:text-5xl">{greeting}</h1>
          <p className="max-w-2xl text-lg text-slate-600">Tell us where you need to be. We&apos;ll compare time, cost, and comfort before asking for consent to book.</p>
        </div>
        <AssistantComposer value={prompt} onChange={setPrompt} onSubmit={submit} loading={planMutation.isPending} />
        {plan ? (
          <div className="flex flex-wrap gap-3">
            <Link href="/plan" className="inline-flex h-10 items-center rounded-md border border-slate-200 bg-white px-4 text-sm font-medium">
              View generated options
            </Link>
          </div>
        ) : null}
      </section>

      <aside className="space-y-4">
        {signedIn ? (
          <>
            <Card>
              <CardHeader><CardTitle>Upcoming journey</CardTitle></CardHeader>
              <CardContent>
                {plan ? (
                  <div className="space-y-2 text-sm">
                    <p className="font-medium">{plan.origin.name} to {plan.destination.name}</p>
                    <p className="text-slate-500">{plan.message}</p>
                    <Link href="/plan" className="text-sm font-medium text-slate-950">Continue planning</Link>
                  </div>
                ) : (
                  <p className="text-sm text-slate-500">No active trip yet. Tell us where you need to be to begin.</p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><WalletCards className="h-4 w-4" /> Journey Account</CardTitle></CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold">{formatInr(balanceQuery.data?.balance ?? 0)}</p>
                <p className="text-sm text-slate-500">Available for simulated bookings and reroutes.</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Recent destinations</CardTitle></CardHeader>
              <CardContent className="space-y-3 text-sm">
                {["Jio Institute", "Mumbai Airport", "Ahmedabad Airport"].map((item) => (
                  <div key={item} className="flex items-center gap-2 text-slate-600"><MapPin className="h-4 w-4" /> {item}</div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Travel DNA</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm text-slate-600">
                <p>Prefers {prefs.data?.prefer_fastest ? "faster" : "balanced"} journeys</p>
                <p>Modes: {(prefs.data?.preferred_modes ?? ["cab", "flight"]).join(", ")}</p>
                <p className="flex items-center gap-2"><Clock className="h-4 w-4" /> Default buffer {prefs.data?.default_buffer_minutes ?? 45} min</p>
              </CardContent>
            </Card>
          </>
        ) : null}
        <BackendStatus online={Boolean(health.data?.status === "ok")} loading={health.isLoading} />
      </aside>
    </div>
  );
}
