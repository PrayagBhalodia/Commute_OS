"use client";

import { useState } from "react";
import { XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export const CANCEL_REASONS = [
  "Change of plans",
  "Schedule changed",
  "Found a better option",
  "Booked by mistake",
  "Other",
] as const;

export function CancelReasonDialog({
  onConfirm,
  onDismiss,
  loading,
}: {
  onConfirm: (reason: { category: string; note?: string }) => void;
  onDismiss: () => void;
  loading?: boolean;
}) {
  const [category, setCategory] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const noteRequired = category === "Other";
  const canSubmit = Boolean(category) && (!noteRequired || note.trim().length > 0);

  return (
    <div className="space-y-3 rounded-lg border border-red-100 bg-red-50/50 p-3">
      <p className="text-sm font-medium text-slate-900">Why are you cancelling this trip?</p>
      <div className="flex flex-wrap gap-2">
        {CANCEL_REASONS.map((reason) => (
          <button
            key={reason}
            type="button"
            onClick={() => setCategory(reason)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              category === reason
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
            )}
          >
            {reason}
          </button>
        ))}
      </div>
      <Textarea
        aria-label="Cancellation details"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder={noteRequired ? "Tell us what happened (required for Other)" : "Anything else we should know? (optional)"}
        className="min-h-20 bg-white text-sm"
      />
      <p className="text-xs text-slate-500">Confirmed legs are refunded to your wallet. Your reason helps us plan better next time.</p>
      <div className="flex gap-2">
        <Button
          variant="danger"
          className="flex-1"
          disabled={!canSubmit || loading}
          onClick={() => category && onConfirm({ category, note: note.trim() || undefined })}
        >
          <XCircle className="h-4 w-4" /> {loading ? "Cancelling" : "Cancel trip"}
        </Button>
        <Button variant="secondary" onClick={onDismiss} disabled={loading}>
          Keep trip
        </Button>
      </div>
    </div>
  );
}
