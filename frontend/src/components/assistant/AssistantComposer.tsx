"use client";

import { Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";

export function AssistantComposer({
  value,
  onChange,
  onSubmit,
  loading,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-2 shadow-soft">
      <div className="flex items-center gap-2 px-2 py-1 text-sm font-medium text-slate-700">
        <Sparkles className="h-4 w-4 text-brand-600" />
        Journey assistant
      </div>
      <Textarea
        aria-label="Journey goal"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Describe your travel goal, timing, luggage, and priorities..."
        className="min-h-32 border-0 shadow-none focus-visible:ring-0"
      />
      <div className="flex justify-end border-t border-slate-100 pt-2">
        <Button onClick={onSubmit} disabled={loading || value.trim().length < 8}>
          <Send className="h-4 w-4" />
          {loading ? "Planning" : "Plan journey"}
        </Button>
      </div>
    </div>
  );
}
