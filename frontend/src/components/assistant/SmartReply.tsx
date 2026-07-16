"use client";

import { useState } from "react";
import { CalendarDays, Check, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PlaceAutocomplete } from "./PlaceAutocomplete";

// The assistant's status tells us exactly which slot it is collecting, so we
// can render the right structured control instead of a free-text box — pinning
// bad input (broad places, "17th July"-style dates) at the source.
const ORIGIN_STATUSES = new Set([
  "waiting_for_origin",
  "awaiting_origin_choice",
  "waiting_for_location_permission",
  "waiting_for_return_origin",
]);
const DESTINATION_STATUSES = new Set([
  "waiting_for_destination",
  "waiting_for_return_destination",
]);
const DATE_STATUSES = new Set(["waiting_for_start_date", "waiting_for_return_date"]);
const TIME_STATUSES = new Set(["waiting_for_start_time", "waiting_for_return_time"]);

/** Whether a structured control (not the free-text box) applies for a status. */
export function hasSmartReply(status?: string): boolean {
  return (
    !!status &&
    (ORIGIN_STATUSES.has(status) ||
      DESTINATION_STATUSES.has(status) ||
      DATE_STATUSES.has(status) ||
      TIME_STATUSES.has(status))
  );
}

export function SmartReply({
  status,
  onSubmit,
  disabled,
}: {
  status?: string;
  onSubmit: (message: string) => void;
  disabled?: boolean;
}) {
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");

  if (!status) return null;

  if (DESTINATION_STATUSES.has(status)) {
    return (
      <PlaceAutocomplete
        placeholder="Search your destination…"
        onSelect={onSubmit}
        disabled={disabled}
      />
    );
  }
  if (ORIGIN_STATUSES.has(status)) {
    return (
      <PlaceAutocomplete
        placeholder="Search your starting point…"
        onSelect={onSubmit}
        disabled={disabled}
      />
    );
  }
  if (DATE_STATUSES.has(status)) {
    return (
      <div className="flex items-center gap-2">
        <label className="flex flex-1 items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5">
          <CalendarDays className="h-4 w-4 shrink-0 text-slate-400" />
          <input
            type="date"
            value={date}
            min={todayIso()}
            disabled={disabled}
            onChange={(event) => setDate(event.target.value)}
            aria-label="Journey date"
            className="w-full bg-transparent py-2 text-sm outline-none disabled:opacity-60"
          />
        </label>
        <Button size="sm" disabled={disabled || !date} onClick={() => onSubmit(date)}>
          <Check className="h-4 w-4" /> Set date
        </Button>
      </div>
    );
  }
  if (TIME_STATUSES.has(status)) {
    return (
      <div className="flex items-center gap-2">
        <label className="flex flex-1 items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5">
          <Clock className="h-4 w-4 shrink-0 text-slate-400" />
          <input
            type="time"
            value={time}
            disabled={disabled}
            onChange={(event) => setTime(event.target.value)}
            aria-label="Journey time"
            className="w-full bg-transparent py-2 text-sm outline-none disabled:opacity-60"
          />
        </label>
        <Button size="sm" disabled={disabled || !time} onClick={() => onSubmit(prettyTime(time))}>
          <Check className="h-4 w-4" /> Set time
        </Button>
      </div>
    );
  }
  return null;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/** "17:00" -> "5:00 PM" for a friendly transcript; the backend parses both. */
function prettyTime(value: string): string {
  const [h, m] = value.split(":").map(Number);
  if (Number.isNaN(h)) return value;
  const meridiem = h >= 12 ? "PM" : "AM";
  const hour = ((h + 11) % 12) + 1;
  return `${hour}:${String(m ?? 0).padStart(2, "0")} ${meridiem}`;
}
