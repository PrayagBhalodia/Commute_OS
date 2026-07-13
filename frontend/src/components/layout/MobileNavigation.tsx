"use client";

import Link from "next/link";
import { Activity, Home, Route, Settings2, WalletCards } from "lucide-react";

const items = [
  { href: "/", label: "Home", icon: Home },
  { href: "/plan", label: "Plan", icon: Route },
  { href: "/active", label: "Active", icon: Activity },
  { href: "/wallet", label: "Wallet", icon: WalletCards },
  { href: "/preferences", label: "DNA", icon: Settings2 },
];

export function MobileNavigation() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-slate-200 bg-white lg:hidden" aria-label="Mobile">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <Link key={item.href} href={item.href} className="flex flex-col items-center gap-1 px-2 py-2 text-xs text-slate-600">
            <Icon className="h-4 w-4" />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
