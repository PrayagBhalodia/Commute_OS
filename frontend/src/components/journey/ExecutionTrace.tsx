import type { ThoughtStep } from "@/models/journey";
import { Badge } from "@/components/ui/badge";

const phaseLabels: Record<string, string> = {
  thought: "Intent parsed",
  action: "Tools called",
  observation: "Options generated",
  decision: "Decision made",
  wait_user: "Confirmation required",
};

export function ExecutionTrace({ steps }: { steps: ThoughtStep[] }) {
  if (!steps.length) return null;
  return (
    <div className="space-y-3">
      {steps.map((step) => (
        <div key={`${step.step_id}-${step.title}`} className="rounded-md border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={step.phase === "wait_user" ? "amber" : "blue"}>{phaseLabels[step.phase] ?? step.phase}</Badge>
            <span className="text-xs text-slate-500">{step.agent ?? "orchestrator"}</span>
          </div>
          <p className="mt-2 text-sm font-medium text-slate-950">{step.title}</p>
          <p className="mt-1 text-sm text-slate-600">{step.detail}</p>
        </div>
      ))}
    </div>
  );
}
