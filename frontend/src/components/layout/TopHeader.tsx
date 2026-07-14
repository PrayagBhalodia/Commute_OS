"use client";

import { useHealth } from "@/hooks/use-health";
import { BackendStatus, SimulatedDataBadge } from "@/components/shared/Status";
import { UserMenu } from "./UserMenu";

export function TopHeader() {
  const health = useHealth();
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 px-4 py-3 backdrop-blur lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <div className="lg:hidden">
            <UserMenu />
          </div>
          <div className="hidden md:block">
            <p className="text-sm font-medium text-slate-950">Tell us where you need to be. We&apos;ll take care of the journey.</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <SimulatedDataBadge />
          <BackendStatus online={Boolean(health.data?.status === "ok")} loading={health.isLoading} />
        </div>
      </div>
    </header>
  );
}
