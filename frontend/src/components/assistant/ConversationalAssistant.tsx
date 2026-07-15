"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, LocateFixed, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { formatInr } from "@/lib/utils";
import type { ChatAction, ChatMessage } from "@/models/chat";
import type { ItineraryOption, PlanResponse } from "@/models/journey";
import { deleteChatSession, sendChatMessage } from "@/services/chat-service";
import { getStoredToken } from "@/services/auth-service";
import { useJourneyStore } from "@/store/journey-store";

const GREETING: ChatMessage = { role: "assistant", text: "Hi, where are you heading today?" };

export function ConversationalAssistant({ onAuthRequired }: { onAuthRequired: () => void }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const userId = useJourneyStore((state) => state.userId);
  const setPlan = useJourneyStore((state) => state.setPlan);
  // Chat transcript and session live in the persisted store so the
  // conversation survives reloads and navigation until the user clears it.
  const storedMessages = useJourneyStore((state) => state.chatMessages);
  const sessionId = useJourneyStore((state) => state.chatSessionId);
  const latest = useJourneyStore((state) => state.chatLatest);
  const appendChatMessage = useJourneyStore((state) => state.appendChatMessage);
  const setChatResponse = useJourneyStore((state) => state.setChatResponse);
  const clearChat = useJourneyStore((state) => state.clearChat);
  const router = useRouter();
  const messages = storedMessages.length ? storedMessages : [GREETING];

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

  async function submit(message = input.trim(), location?: GeolocationCoordinates) {
    if (!message || loading) return;
    if (!getStoredToken()) {
      onAuthRequired();
      return;
    }
    setInput("");
    appendChatMessage({ role: "user", text: message });
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
      setChatResponse(response);
      const planned = response.tool_results.find((item) => item.ok && item.tool === "plan_journey")?.data;
      if (planned) {
        setPlan({ ...planned, chain_of_thought: planned.chain_of_thought ?? [] } as PlanResponse);
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
        void submit(action.message, position.coords);
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

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-soft">
      {storedMessages.length ? (
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2">
          <p className="text-xs font-medium text-slate-500">Journey assistant</p>
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
        </div>
      ) : null}
      {messages.length ? (
        <div className="max-h-[420px] space-y-3 overflow-y-auto border-b border-slate-100 p-4" aria-live="polite">
          {messages.map((message, index) => (
            <div key={`${message.role}-${index}`} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
              <p className={`max-w-[88%] whitespace-pre-line rounded-md px-3 py-2 text-sm leading-6 ${message.role === "user" ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-800"}`}>
                {message.text}
              </p>
            </div>
          ))}

          {latest?.leg_option_groups.map((group) => (
            <section key={group.leg_number} className="border-t border-slate-100 pt-3">
              <h3 className="text-sm font-semibold">Leg {group.leg_number}: {group.origin} to {group.destination}</h3>
              <div className="mt-2 flex flex-wrap gap-2">
                {group.options.map((option, index) => (
                  <Button key={option.leg_id} variant="secondary" size="sm" onClick={() => void submit(`Leg ${group.leg_number} option ${index + 1}`)} disabled={loading}>
                    {option.mode} · {String(option.metadata.specification ?? option.operator)} · {formatInr(option.price)}
                  </Button>
                ))}
              </div>
            </section>
          ))}

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

          {latest?.suggested_actions.length ? (
            <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
              {latest.suggested_actions.map((action) => (
                <Button key={action.id} variant={action.kind === "confirm" ? "primary" : "secondary"} size="sm" onClick={() => runAction(action)} disabled={loading}>
                  {action.kind === "location" ? <LocateFixed className="h-4 w-4" /> : null}
                  {action.label}
                </Button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="p-2">
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
    </div>
  );
}
