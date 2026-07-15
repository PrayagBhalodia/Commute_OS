"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { CalendarClock, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Split "YYYY-MM-DDTHH:mm" into its date and time parts. */
function splitLocal(value?: string): { date: string; time: string } {
  if (!value || !value.includes("T")) return { date: "", time: "" };
  const [date, time = ""] = value.split("T");
  return { date, time: time.slice(0, 5) };
}

const joinLocal = (date: string, time: string) => (date && time ? `${date}T${time}` : "");

export interface DateTimeModalResult {
  startDateTime: string;
  returnDateTime?: string;
}

/**
 * Reusable date/time capture dialog.
 *
 * Used in two scenarios that share the exact same styling:
 *  - `withReturn = false`: prompt only for Start Date + Start Time (shown when
 *    the trip description has no explicit timing).
 *  - `withReturn = true`: additionally prompt for Return Date + Return Time
 *    (shown when the user ticks "Return journey").
 */
export function DateTimeModal({
  open,
  withReturn,
  initialStart,
  initialReturn,
  loading,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  withReturn: boolean;
  initialStart?: string;
  initialReturn?: string;
  loading?: boolean;
  onCancel: () => void;
  onConfirm: (result: DateTimeModalResult) => void;
}) {
  const [startDate, setStartDate] = useState("");
  const [startTime, setStartTime] = useState("");
  const [returnDate, setReturnDate] = useState("");
  const [returnTime, setReturnTime] = useState("");

  // Seed fields whenever the dialog (re)opens, defaulting to sensible values.
  useEffect(() => {
    if (!open) return;
    const start = splitLocal(initialStart);
    const ret = splitLocal(initialReturn);
    const today = new Date().toISOString().slice(0, 10);
    setStartDate(start.date || today);
    setStartTime(start.time || "09:00");
    setReturnDate(ret.date || start.date || today);
    setReturnTime(ret.time || "18:00");
  }, [open, initialStart, initialReturn]);

  // Close on Escape.
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === "Escape" && !loading) onCancel();
    },
    [loading, onCancel],
  );

  const startValue = joinLocal(startDate, startTime);
  const returnValue = joinLocal(returnDate, returnTime);

  const returnBeforeStart = useMemo(
    () => Boolean(withReturn && startValue && returnValue && new Date(returnValue) <= new Date(startValue)),
    [withReturn, startValue, returnValue],
  );

  const canContinue =
    Boolean(startValue) && (!withReturn || (Boolean(returnValue) && !returnBeforeStart));

  const submit = () => {
    if (!canContinue) return;
    onConfirm({ startDateTime: startValue, returnDateTime: withReturn ? returnValue : undefined });
  };

  // Conditional render (no AnimatePresence) so closing is instant + reliable;
  // the entrance is still animated via the motion components below.
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onKeyDown={handleKeyDown}
    >
      {/* Backdrop */}
      <motion.div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        onClick={() => !loading && onCancel()}
        aria-hidden="true"
      />
          {/* Dialog */}
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="datetime-modal-title"
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
            className="relative z-10 w-full max-w-md rounded-lg border border-slate-200 bg-white shadow-soft"
          >
            <div className="flex items-start justify-between gap-3 p-5 pb-3">
              <div className="flex items-center gap-2">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-50 text-brand-700">
                  <CalendarClock className="h-5 w-5" />
                </span>
                <div>
                  <h2 id="datetime-modal-title" className="text-base font-semibold text-slate-950">
                    {withReturn ? "When are you travelling?" : "When do you want to start?"}
                  </h2>
                  <p className="text-sm text-slate-500">
                    {withReturn
                      ? "Set your departure and return so we can time every leg."
                      : "We couldn't spot a time in your trip — pick a start."}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => !loading && onCancel()}
                aria-label="Close"
                className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-4 p-5 pt-2">
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium text-slate-900">Start</legend>
                <div className="grid grid-cols-2 gap-3">
                  <label className="block text-xs font-medium text-slate-600">
                    Date
                    <Input
                      autoFocus
                      type="date"
                      className="mt-1"
                      value={startDate}
                      onChange={(event) => setStartDate(event.target.value)}
                      aria-label="Start date"
                    />
                  </label>
                  <label className="block text-xs font-medium text-slate-600">
                    Time
                    <Input
                      type="time"
                      className="mt-1"
                      value={startTime}
                      onChange={(event) => setStartTime(event.target.value)}
                      aria-label="Start time"
                    />
                  </label>
                </div>
              </fieldset>

              {withReturn ? (
                <fieldset className="space-y-2">
                  <legend className="text-sm font-medium text-slate-900">Return</legend>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="block text-xs font-medium text-slate-600">
                      Date
                      <Input
                        type="date"
                        className="mt-1"
                        value={returnDate}
                        min={startDate}
                        onChange={(event) => setReturnDate(event.target.value)}
                        aria-label="Return date"
                      />
                    </label>
                    <label className="block text-xs font-medium text-slate-600">
                      Time
                      <Input
                        type="time"
                        className="mt-1"
                        value={returnTime}
                        onChange={(event) => setReturnTime(event.target.value)}
                        aria-label="Return time"
                      />
                    </label>
                  </div>
                </fieldset>
              ) : null}

              {returnBeforeStart ? (
                <p role="alert" className="text-xs font-medium text-red-600">
                  Return must be after the start time.
                </p>
              ) : null}

              <div className="flex gap-2 pt-1">
                <Button type="button" className="flex-1" disabled={!canContinue || loading} onClick={submit}>
                  {loading ? "Planning" : "Continue"}
                </Button>
                <Button type="button" variant="secondary" disabled={loading} onClick={() => onCancel()}>
                  Cancel
                </Button>
              </div>
            </div>
          </motion.div>
    </div>
  );
}
