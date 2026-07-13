"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, CalendarClock, History, Home, Route, Settings2, WalletCards } from "lucide-react";
import { cn } from "@/lib/utils";

const items = [
  { href: "/", label: "Home", icon: Home },
  { href: "/plan", label: "Plan", icon: Route },
  { href: "/active", label: "Active", icon: Activity },
  { href: "/wallet", label: "Wallet", icon: WalletCards },
  { href: "/preferences", label: "Travel DNA", icon: Settings2 },
  { href: "/history", label: "History", icon: History },
];

export function AppSidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white/80 px-4 py-5 lg:block">
      <Link href="/" className="flex items-center gap-3 px-2" aria-label="Commute OS home">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-slate-950 text-white">
          <CalendarClock className="h-5 w-5" />
        </div>
        <div>
          <p className="font-semibold">Commute OS</p>
          <p className="text-xs text-slate-500">Journey Operating System</p>
        </div>
      </Link>
      <nav className="mt-8 space-y-1" aria-label="Primary">
        {items.map((item) => {
          const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-950",
                active && "bg-slate-100 text-slate-950",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
