"use client";

const levels = [
  { value: "manual", label: "Manual", description: "You approve every booking, reroute, and wallet movement." },
  { value: "smart", label: "Smart approval", description: "The OS prepares actions and asks when cost, risk, or arrival time changes." },
  { value: "auto", label: "Full auto", description: "The OS may reroute and reconcile within your saved rules." },
];

export function AutonomySelector({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {levels.map((level) => (
        <button
          key={level.value}
          type="button"
          onClick={() => onChange(level.value)}
          className={`rounded-lg border p-4 text-left transition ${value === level.value ? "border-brand-500 bg-brand-50" : "border-slate-200 bg-slate-50 hover:bg-white"}`}
        >
          <p className="font-semibold">{level.label}</p>
          <p className="mt-2 text-sm text-slate-600">{level.description}</p>
        </button>
      ))}
    </div>
  );
}
