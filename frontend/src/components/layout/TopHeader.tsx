"use client";

import { useHealth } from "@/hooks/use-health";
import { BackendStatus, SimulatedDataBadge } from "@/components/shared/Status";

export function TopHeader() {
  const health = useHealth();
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 px-4 py-3 backdrop-blur lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-950">Tell us where you need to be. We&apos;ll take care of the journey.</p>
          <p className="text-xs text-slate-500">Bookings, payments, and disruptions are simulated.</p>
        </div>
        <div className="flex items-center gap-2">
          <SimulatedDataBadge />
          <BackendStatus online={Boolean(health.data?.status === "ok")} loading={health.isLoading} />
        </div>
      </div>
    </header>
  );
}
