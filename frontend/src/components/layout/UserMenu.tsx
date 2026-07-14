"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronUp, KeyRound, Loader2, LogIn, LogOut, Save, Settings2, UserRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { usePreferencesController } from "@/controllers/journey-controller";
import { DEMO_USER_ID } from "@/constants/demo";
import { PRIORITY_LABELS, TRIP_PRIORITIES, type TripPriority } from "@/lib/priority";
import type { UserPreferences } from "@/models/preferences";
import {
  changePassword,
  getStoredUser,
  logout,
  updateAccount,
  type AuthUser,
} from "@/services/auth-service";
import { updatePreferences } from "@/services/preferences-service";
import { useJourneyStore } from "@/store/journey-store";

const MODE_OPTIONS = ["cab", "auto", "metro", "bus", "train", "flight"] as const;

export function UserMenu({ openUp = false }: { openUp?: boolean } = {}) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"preferences" | "account">("preferences");
  const panelRef = useRef<HTMLDivElement>(null);
  const setUserId = useJourneyStore((state) => state.setUserId);

  useEffect(() => {
    const stored = getStoredUser();
    setUser(stored);
    // Tie journeys, wallet, and preferences to the signed-in account.
    setUserId(stored ? stored.id : DEMO_USER_ID);
  }, [setUserId]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!user) {
    return (
      <Link
        href="/auth"
        className="inline-flex h-9 items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        <LogIn className="h-3.5 w-3.5" /> Sign in
      </Link>
    );
  }

  const initial = (user.name || user.email)[0]?.toUpperCase() ?? "U";

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="User settings"
        className="focus-ring inline-flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white pl-1.5 pr-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-950 text-xs font-semibold text-white">
          {initial}
        </span>
        <span className="hidden max-w-36 truncate sm:block">{user.name || user.email}</span>
        <ChevronUp className={cn("h-3.5 w-3.5 text-slate-400 transition", open && "rotate-180")} />
      </button>

      {open ? (
        <div
          className={cn(
            "absolute left-0 z-50 w-[22rem] rounded-lg border border-slate-200 bg-white p-4 shadow-soft sm:w-96",
            openUp ? "bottom-full mb-2" : "top-full mt-2",
          )}
        >
          <div className="flex items-center gap-3 border-b border-slate-100 pb-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-950 text-sm font-semibold text-white">
              {initial}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-950">{user.name || "Traveller"}</p>
              <p className="truncate text-xs text-slate-500">{user.email}</p>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-1 rounded-md bg-slate-100 p-1 text-sm font-medium">
            <button
              type="button"
              className={cn("focus-ring flex items-center justify-center gap-1.5 rounded px-2 py-1.5", tab === "preferences" ? "bg-white text-slate-950 shadow-sm" : "text-slate-600")}
              onClick={() => setTab("preferences")}
            >
              <Settings2 className="h-3.5 w-3.5" /> Preferences
            </button>
            <button
              type="button"
              className={cn("focus-ring flex items-center justify-center gap-1.5 rounded px-2 py-1.5", tab === "account" ? "bg-white text-slate-950 shadow-sm" : "text-slate-600")}
              onClick={() => setTab("account")}
            >
              <UserRound className="h-3.5 w-3.5" /> Account
            </button>
          </div>

          <div className="mt-4 max-h-[26rem] overflow-y-auto pr-1">
            {tab === "preferences" ? <PreferencesTab userId={user.id} /> : <AccountTab user={user} onUserChange={setUser} />}
          </div>

          <div className="mt-4 border-t border-slate-100 pt-3">
            <Button
              variant="secondary"
              size="sm"
              className="w-full text-red-600 hover:bg-red-50"
              onClick={async () => {
                await logout();
                window.location.href = "/";
              }}
            >
              <LogOut className="h-3.5 w-3.5" /> Sign out
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function PreferencesTab({ userId }: { userId: string }) {
  const prefsQuery = usePreferencesController(userId);
  const queryClient = useQueryClient();
  // Journey style is the shared optimisation lens (Time / Cost / Comfort) that
  // also drives the Plan page — both read and write the same store value.
  const priority = useJourneyStore((state) => state.priority);
  const setPriority = useJourneyStore((state) => state.setPriority);
  const [modes, setModes] = useState<string[]>([]);
  const loadedFor = useRef<string | null>(null);

  useEffect(() => {
    const data = prefsQuery.data;
    if (!data || loadedFor.current === data.user_id) return;
    loadedFor.current = data.user_id;
    setModes(data.preferred_modes ?? []);
  }, [prefsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: (prefs: UserPreferences) => updatePreferences(prefs),
    onSuccess: (prefs) => {
      toast.success("Default preferences saved");
      void queryClient.invalidateQueries({ queryKey: ["preferences", prefs.user_id] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (prefsQuery.isLoading) {
    return (
      <p className="flex items-center gap-2 py-6 text-sm text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading your preferences…
      </p>
    );
  }

  function save() {
    const base = prefsQuery.data ?? ({ user_id: userId } as UserPreferences);
    // Map the shared journey-style lens onto the backend preference flags.
    saveMutation.mutate({
      ...base,
      user_id: userId,
      prefer_fastest: priority === "time",
      prefer_cheapest: priority === "cost",
      prefer_comfort: priority === "comfort",
      preferred_modes: modes,
    });
  }

  return (
    <div className="space-y-4 text-sm">
      <fieldset>
        <legend className="mb-1.5 font-medium text-slate-700">Journey style</legend>
        <div className="grid grid-cols-3 gap-1 rounded-md bg-slate-100 p-1" role="group" aria-label="Journey style">
          {TRIP_PRIORITIES.map((option: TripPriority) => (
            <button
              key={option}
              type="button"
              aria-pressed={priority === option}
              className={cn("focus-ring rounded px-2 py-1.5", priority === option ? "bg-white font-medium text-slate-950 shadow-sm" : "text-slate-600")}
              onClick={() => setPriority(option)}
            >
              {PRIORITY_LABELS[option]}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-slate-400">Kept in sync with the Plan page.</p>
      </fieldset>

      <fieldset>
        <legend className="mb-1.5 font-medium text-slate-700">Preferred modes</legend>
        <div className="grid grid-cols-3 gap-2">
          {MODE_OPTIONS.map((mode) => (
            <label key={mode} className="flex cursor-pointer items-center gap-2 rounded-md border border-slate-200 px-2.5 py-1.5 capitalize hover:bg-slate-50">
              <input
                type="checkbox"
                className="accent-slate-900"
                checked={modes.includes(mode)}
                onChange={(e) => setModes((prev) => (e.target.checked ? [...prev, mode] : prev.filter((m) => m !== mode)))}
              />
              {mode}
            </label>
          ))}
        </div>
      </fieldset>

      <Button size="sm" className="w-full" disabled={saveMutation.isPending} onClick={save}>
        {saveMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
        Save preferences
      </Button>
    </div>
  );
}

function AccountTab({ user, onUserChange }: { user: AuthUser; onUserChange: (user: AuthUser) => void }) {
  const [name, setName] = useState(user.name ?? "");
  const [phone, setPhone] = useState(user.phone ?? "");
  const [savingAccount, setSavingAccount] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);

  async function saveAccount() {
    setSavingAccount(true);
    try {
      const result = await updateAccount({ name, phone });
      onUserChange(result.user);
      toast.success(result.message);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not update account.");
    } finally {
      setSavingAccount(false);
    }
  }

  async function savePassword() {
    if (newPassword.length < 8) {
      toast.error("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("New passwords do not match.");
      return;
    }
    setSavingPassword(true);
    try {
      const result = await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      toast.success(result.message);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not change password.");
    } finally {
      setSavingPassword(false);
    }
  }

  return (
    <div className="space-y-4 text-sm">
      <div className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-500">
        Signed in with {user.provider === "google" ? "Google" : "email & password"} · {user.email}
      </div>

      <label className="block space-y-1">
        <span className="font-medium text-slate-700">Full name</span>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
      </label>
      <label className="block space-y-1">
        <span className="font-medium text-slate-700">Mobile number</span>
        <Input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" />
      </label>
      <Button size="sm" className="w-full" disabled={savingAccount} onClick={saveAccount}>
        {savingAccount ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
        Save account
      </Button>

      {user.provider === "password" ? (
        <div className="space-y-3 border-t border-slate-100 pt-3">
          <p className="font-medium text-slate-700">Change password</p>
          <Input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder="Current password"
            autoComplete="current-password"
          />
          <Input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="New password (min 8 characters)"
            autoComplete="new-password"
          />
          <Input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Confirm new password"
            autoComplete="new-password"
          />
          <Button variant="secondary" size="sm" className="w-full" disabled={savingPassword} onClick={savePassword}>
            {savingPassword ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
            Update password
          </Button>
        </div>
      ) : null}
    </div>
  );
}
