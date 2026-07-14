"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, CalendarClock, History, Home, PanelLeft, PanelLeftClose, Route, Settings2, WalletCards } from "lucide-react";
import { cn } from "@/lib/utils";
import { UserMenu } from "./UserMenu";

const items = [
  { href: "/", label: "Home", icon: Home },
  { href: "/plan", label: "Plan", icon: Route },
  { href: "/active", label: "Active", icon: Activity },
  { href: "/wallet", label: "Wallet", icon: WalletCards },
  { href: "/preferences", label: "Travel DNA", icon: Settings2 },
  { href: "/history", label: "History", icon: History },
];

export function AppSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const pathname = usePathname();
  return (
    <aside
      className={cn(
        "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-slate-200 bg-white/80 py-5 lg:flex",
        collapsed ? "w-20 items-center px-2" : "w-64 px-4",
      )}
    >
      {collapsed ? (
        <div className="flex flex-col items-center gap-3">
          <Link
            href="/"
            className="flex h-9 w-9 items-center justify-center rounded-md bg-slate-950 text-white"
            aria-label="Commute OS home"
          >
            <CalendarClock className="h-5 w-5" />
          </Link>
          <button
            type="button"
            onClick={onToggle}
            aria-label="Open sidebar"
            className="focus-ring flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-950"
          >
            <PanelLeft className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between gap-2 px-2">
            <Link href="/" className="flex items-center gap-3" aria-label="Commute OS home">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-slate-950 text-white">
                <CalendarClock className="h-5 w-5" />
              </div>
              <div>
                <p className="font-semibold">Commute OS</p>
                <p className="text-xs text-slate-500">Journey Operating System</p>
              </div>
            </Link>
            <button
              type="button"
              onClick={onToggle}
              aria-label="Close sidebar"
              className="focus-ring flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-950"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          </div>

          <nav className="mt-8 flex-1 space-y-1 overflow-y-auto" aria-label="Primary">
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

          <div className="mt-4 border-t border-slate-100 pt-4">
            <UserMenu openUp />
          </div>
        </>
      )}
    </aside>
  );
}
