"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { apiClient } from "@/services/api-client";
import { clearSession, getStoredToken } from "@/services/auth-service";
import { AppSidebar } from "./AppSidebar";
import { MobileNavigation } from "./MobileNavigation";
import { TopHeader } from "./TopHeader";

// Only the landing page and the auth flow are public; every feature page
// requires a signed-in user.
function isPublicPath(pathname: string) {
  return pathname === "/" || pathname.startsWith("/auth");
}

function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const verifiedRef = useRef(false);
  const [allowed, setAllowed] = useState(() => isPublicPath(pathname));

  useEffect(() => {
    if (isPublicPath(pathname)) {
      setAllowed(true);
      return;
    }
    const token = getStoredToken();
    const authUrl = `/auth?next=${encodeURIComponent(pathname)}`;
    if (!token) {
      setAllowed(false);
      router.replace(authUrl);
      return;
    }
    setAllowed(true);
    if (!verifiedRef.current) {
      verifiedRef.current = true;
      apiClient
        .get("/auth/me", { headers: { Authorization: `Bearer ${token}` } })
        .catch((err: { status?: number }) => {
          // Only force sign-in on a rejected session; a network error just
          // means the backend is offline and pages already handle that.
          if (err?.status === 401) {
            clearSession();
            setAllowed(false);
            router.replace(authUrl);
          }
        });
    }
  }, [pathname, router]);

  if (!allowed) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center gap-2 text-sm text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Taking you to sign in…
      </div>
    );
  }
  return <>{children}</>;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname.startsWith("/auth")) {
    return <>{children}</>;
  }
  return (
    <div className="min-h-screen lg:flex">
      <AppSidebar />
      <div className="min-w-0 flex-1 pb-16 lg:pb-0">
        <TopHeader />
        <main className="mx-auto w-full max-w-7xl px-4 py-6 lg:px-8">
          <AuthGuard>{children}</AuthGuard>
        </main>
      </div>
      <MobileNavigation />
    </div>
  );
}
