"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Compass,
  Loader2,
  LocateFixed,
  MessageCircleQuestion,
  Send,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { SmartReply, hasSmartReply } from "./SmartReply";
import { PlaceAutocomplete } from "./PlaceAutocomplete";
import { formatInr } from "@/lib/utils";
import type { ChatAction, ChatMessage } from "@/models/chat";
import type { ItineraryOption, PlanResponse } from "@/models/journey";
import { askKnowledge, deleteChatSession, sendChatMessage } from "@/services/chat-service";
import { getStoredToken } from "@/services/auth-service";
import { useJourneyStore } from "@/store/journey-store";

const GREETING: ChatMessage = { role: "assistant", text: "Hi, where are you heading today?" };

// Starter questions for the RAG-backed "Ask a question" mode.
const EXAMPLE_QUESTIONS = [
  "How early should I reach the airport?",
  "What is the baggage policy?",
  "Cancellation and refund rules?",
  "Is the metro wheelchair accessible?",
];

type AssistantMode = "choose" | "plan" | "ask";
interface AskItem {
  q: string;
  a: string;
  sources: string[];
}

export function ConversationalAssistant({ onAuthRequired }: { onAuthRequired: () => void }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<AssistantMode>("choose");
  const [askItems, setAskItems] = useState<AskItem[]>([]);
  const [askInput, setAskInput] = useState("");
  const [askLoading, setAskLoading] = useState(false);
  const userId = useJourneyStore((state) => state.userId);
  const setPlan = useJourneyStore((state) => state.setPlan);
  // Chat transcript and session live in the persisted store so the
  // conversation survives reloads and navigation until the user clears it.
  const storedMessages = useJourneyStore((state) => state.chatMessages);
  const sessionId = useJourneyStore((state) => state.chatSessionId);
  const latest = useJourneyStore((state) => state.chatLatest);
  const appendChatMessage = useJourneyStore((state) => state.appendChatMessage);
  const setChatResponse = useJourneyStore((state) => state.setChatResponse);
  const updateChatResponse = useJourneyStore((state) => state.updateChatResponse);
  const clearChat = useJourneyStore((state) => state.clearChat);
  const router = useRouter();
  const messages = storedMessages.length ? storedMessages : [GREETING];
  // Keep the transcript pinned to the newest message so the user never has to
  // scroll down after sending — the scroll container snaps to the bottom
  // whenever messages, results, or the loading state change.
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [storedMessages, latest, loading]);

  async function handleClear() {
    if (sessionId) {
      try {
        await deleteChatSession(sessionId);
      } catch {
        // Server-side cleanup is best-effort; the local session resets anyway.
      }
    }
    clearChat();
  }

  async function submit(
    message = input.trim(),
    { location, quiet = false }: { location?: GeolocationCoordinates; quiet?: boolean } = {},
  ) {
    if (!message || loading) return;
    if (!getStoredToken()) {
      onAuthRequired();
      return;
    }
    // "Quiet" turns (tweaking a leg option) refresh the live review in place
    // rather than posting the click as a chat bubble and repeating the whole
    // review back — so the user's transcript isn't spammed on every change.
    if (!quiet) {
      setInput("");
      appendChatMessage({ role: "user", text: message });
    }
    setLoading(true);
    try {
      const response = await sendChatMessage({
        session_id: sessionId,
        user_id: userId,
        message,
        client_time: new Date().toISOString(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        ...(location
          ? {
              // No label on purpose: the backend reverse-geocodes the
              // coordinates and uses the real place name everywhere.
              current_lat: location.latitude,
              current_lng: location.longitude,
            }
          : {}),
      });
      if (quiet) updateChatResponse(response);
      else setChatResponse(response);
      const planned = response.tool_results.find((item) => item.ok && item.tool === "plan_journey")?.data;
      if (planned) {
        setPlan({ ...planned, chain_of_thought: planned.chain_of_thought ?? [] } as PlanResponse);
        // Every journey detail is collected and a plan now exists — hand off to
        // the richer Plan workspace to compare options, see the reasoning, and
        // proceed to booking.
        router.push("/plan");
      }
      const composed = response.tool_results.find(
        (item) => item.ok && item.tool === "compose_journey",
      )?.data as unknown as ItineraryOption | undefined;
      if (composed?.itinerary_id) {
        const current = useJourneyStore.getState().activePlan;
        if (current) {
          useJourneyStore.setState({
            activePlan: {
              ...current,
              itineraries: [
                ...current.itineraries.filter(
                  (item) => item.itinerary_id !== composed.itinerary_id,
                ),
                composed,
              ],
              selected_itinerary_id: composed.itinerary_id,
            },
            selectedItineraryId: composed.itinerary_id,
          });
        }
      } else if (response.journey_review?.itinerary_id) {
        useJourneyStore.getState().selectItinerary(response.journey_review.itinerary_id);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The journey assistant could not respond.");
    } finally {
      setLoading(false);
    }
  }

  function requestLocation(action: ChatAction) {
    if (!navigator.geolocation) {
      toast.error("Location is not available in this browser. Enter your origin manually.");
      return;
    }
    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLoading(false);
        void submit(action.message, { location: position.coords });
      },
      () => {
        setLoading(false);
        toast.error("Location permission was not granted. You can enter your origin manually.");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  }

  function runAction(action: ChatAction) {
    if (action.kind === "location") requestLocation(action);
    else if (action.kind === "link" && action.href) router.push(action.href);
    else void submit(action.message);
  }

  async function submitAsk(question = askInput.trim()) {
    if (!question || askLoading) return;
    setAskInput("");
    setAskItems((prev) => [...prev, { q: question, a: "", sources: [] }]);
    setAskLoading(true);
    try {
      const res = await askKnowledge(question);
      const sources = Array.from(new Set(res.citations.map((item) => item.source)));
      setAskItems((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = { q: question, a: res.answer, sources };
        return copy;
      });
    } catch (error) {
      setAskItems((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = {
          q: question,
          a: "Sorry — I couldn't reach the knowledge base just now. Please try again.",
          sources: [],
        };
        return copy;
      });
      toast.error(error instanceof Error ? error.message : "Could not fetch the answer.");
    } finally {
      setAskLoading(false);
    }
  }

  // A live journey transcript always continues in plan mode; otherwise honour
  // the button the traveller picked on the landing choice.
  const effectiveMode: AssistantMode = storedMessages.length ? "plan" : mode;
  const status = latest?.state.status;
  // The very first destination entry has no status yet, so force the place
  // autocomplete; after that, follow the assistant's real slot status.
  const isFirstEntry = effectiveMode === "plan" && storedMessages.length === 0;
  const smartStatus = isFirstEntry ? "waiting_for_destination" : status;
  const showSmartReply = isFirstEntry || hasSmartReply(status);
  const visibleActions = latest?.suggested_actions ?? [];

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-soft">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2">
        <p className="text-xs font-medium text-slate-500">Journey assistant</p>
        {storedMessages.length ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-slate-500 hover:text-red-600"
            onClick={() => void handleClear()}
            disabled={loading}
          >
            <Trash2 className="h-3.5 w-3.5" /> Clear chat
          </Button>
        ) : effectiveMode !== "choose" ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-slate-500"
            onClick={() => {
              setMode("choose");
              setAskItems([]);
            }}
            disabled={loading || askLoading}
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back
          </Button>
        ) : null}
      </div>

      {effectiveMode === "choose" ? (
        <div className="grid gap-3 p-4 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => setMode("plan")}
            className="flex flex-col items-start gap-2 rounded-lg border border-slate-200 bg-white p-4 text-left transition hover:border-brand-400 hover:bg-brand-50"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-100 text-brand-700">
              <Compass className="h-5 w-5" />
            </span>
            <span className="text-sm font-semibold text-slate-800">Plan a journey</span>
            <span className="text-xs text-slate-500">
              Tell us where you&apos;re going. We&apos;ll compare time, cost, and comfort.
            </span>
          </button>
          <button
            type="button"
            onClick={() => setMode("ask")}
            className="flex flex-col items-start gap-2 rounded-lg border border-slate-200 bg-white p-4 text-left transition hover:border-brand-400 hover:bg-brand-50"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-100 text-brand-700">
              <MessageCircleQuestion className="h-5 w-5" />
            </span>
            <span className="text-sm font-semibold text-slate-800">Ask a question</span>
            <span className="text-xs text-slate-500">
              Baggage, airport timing, refunds, accessibility — answered from our guides.
            </span>
          </button>
        </div>
      ) : null}

      {effectiveMode === "ask" ? (
        <>
          <div ref={scrollRef} className="max-h-[420px] space-y-3 overflow-y-auto border-b border-slate-100 p-4" aria-live="polite">
            {askItems.length === 0 ? (
              <div className="space-y-3">
                <p className="text-sm text-slate-600">Ask about travel policies and guidance. Try:</p>
                <div className="flex flex-wrap gap-2">
                  {EXAMPLE_QUESTIONS.map((question) => (
                    <Button key={question} variant="secondary" size="sm" onClick={() => void submitAsk(question)} disabled={askLoading}>
                      {question}
                    </Button>
                  ))}
                </div>
              </div>
            ) : null}

            {askItems.map((item, index) => (
              <div key={index} className="space-y-2">
                <div className="flex justify-end">
                  <p className="max-w-[88%] rounded-md bg-brand-600 px-3 py-2 text-sm text-white">{item.q}</p>
                </div>
                {item.a ? (
                  <div className="flex justify-start">
                    <div className="max-w-[92%] rounded-md bg-slate-100 px-3 py-2 text-sm leading-6 text-slate-800">
                      <p className="whitespace-pre-line">{item.a}</p>
                      {item.sources.length ? (
                        <p className="mt-1 text-[11px] text-slate-400">Sources: {item.sources.join(", ")}</p>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
            ))}

            {askLoading ? (
              <div className="flex justify-start" aria-label="Fetching answer">
                <div className="flex items-center gap-1 rounded-md bg-slate-100 px-3 py-3">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:0ms]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:150ms]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:300ms]" />
                </div>
              </div>
            ) : null}
          </div>

          <div className="p-2">
            <Textarea
              aria-label="Ask a question"
              value={askInput}
              onChange={(event) => setAskInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submitAsk();
                }
              }}
              placeholder="Ask about baggage, airport timing, refunds…"
              className="min-h-16 border-0 shadow-none focus-visible:ring-0"
            />
            <div className="flex justify-end border-t border-slate-100 pt-2">
              <Button onClick={() => void submitAsk()} disabled={askLoading || !askInput.trim()} aria-label="Ask question">
                {askLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Ask
              </Button>
            </div>
          </div>
        </>
      ) : null}

      {effectiveMode === "plan" ? (
        <>
        <div ref={scrollRef} className="max-h-[420px] space-y-3 overflow-y-auto border-b border-slate-100 p-4" aria-live="polite">
          {messages.map((message, index) => (
            <div key={`${message.role}-${index}`} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
              <p className={`max-w-[88%] whitespace-pre-line rounded-md px-3 py-2 text-sm leading-6 ${message.role === "user" ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-800"}`}>
                {message.text}
              </p>
            </div>
          ))}

          {loading ? (
            <div className="flex justify-start" aria-label="Assistant is typing">
              <div className="flex items-center gap-1 rounded-md bg-slate-100 px-3 py-3">
                <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:0ms]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:150ms]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:300ms]" />
              </div>
            </div>
          ) : null}

          {latest?.leg_option_groups.map((group) => {
            const selectedLegId = latest?.state.selected_leg_ids?.[String(group.leg_number)];
            return (
              <section key={group.leg_number} className="border-t border-slate-100 pt-3">
                <h3 className="text-sm font-semibold">Leg {group.leg_number}: {group.origin} to {group.destination}</h3>
                <div className="mt-2 flex flex-wrap gap-2">
                  {group.options.map((option, index) => {
                    const selected = selectedLegId
                      ? option.leg_id === selectedLegId
                      : option.leg_id === group.default_leg_id;
                    return (
                      <Button
                        key={option.leg_id}
                        variant={selected ? "primary" : "secondary"}
                        size="sm"
                        aria-pressed={selected}
                        // Quiet turn: updates the review pricing in place instead
                        // of posting the click and repeating the whole review.
                        onClick={() => void submit(`Leg ${group.leg_number} option ${index + 1}`, { quiet: true })}
                        disabled={loading}
                      >
                        {option.mode} · {String(option.metadata.specification ?? option.operator)} · {formatInr(option.price)}
                      </Button>
                    );
                  })}
                </div>
              </section>
            );
          })}

          {latest?.journey_review ? (
            <section className="border-t border-slate-200 pt-3">
              <h3 className="text-sm font-semibold">Journey review</h3>
              <div className="mt-2 space-y-1 text-sm text-slate-600">
                {latest.journey_review.legs.map((leg, index) => (
                  <p key={leg.leg_id}>{index + 1}. {leg.origin} to {leg.destination} · {leg.mode} · {formatInr(leg.price)}</p>
                ))}
                <p className="pt-1 font-semibold text-slate-950">Total {formatInr(latest.journey_review.total_price)} · {Math.round(latest.journey_review.total_duration_minutes)} min</p>
              </div>
            </section>
          ) : null}

          {visibleActions.length ? (
            <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
              {visibleActions.map((action) => (
                <Button key={action.id} variant={action.kind === "confirm" ? "primary" : "secondary"} size="sm" onClick={() => runAction(action)} disabled={loading}>
                  {action.kind === "location" ? <LocateFixed className="h-4 w-4" /> : null}
                  {action.label}
                </Button>
              ))}
            </div>
          ) : null}
        </div>

        <div className="p-2">
        {showSmartReply ? (
          <div className="mb-2">
            <SmartReply status={smartStatus} onSubmit={(message) => void submit(message)} disabled={loading} />
          </div>
        ) : null}
        <Textarea
          aria-label="Journey request"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder="Where do you need to go, and when?"
          className="min-h-24 border-0 shadow-none focus-visible:ring-0"
        />
        <div className="flex justify-end border-t border-slate-100 pt-2">
          <Button onClick={() => void submit()} disabled={loading || !input.trim()} aria-label="Send message">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Send
          </Button>
        </div>
      </div>
        </>
      ) : null}
    </div>
  );
}
