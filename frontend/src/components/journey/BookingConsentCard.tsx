"use client";

import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

export function BookingConsentCard({
  consent,
  onConsent,
  onConfirm,
  loading,
  disabled,
}: {
  consent: boolean;
  onConsent: (value: boolean) => void;
  onConfirm: () => void;
  loading?: boolean;
  disabled?: boolean;
}) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
      <div className="flex gap-3">
        <ShieldAlert className="mt-0.5 h-5 w-5 text-amber-700" />
        <div>
          <p className="font-semibold text-amber-950">Explicit consent required</p>
          <p className="mt-1 text-sm text-amber-800">This prototype simulates bookings and wallet debits. The backend will not book until consent is true.</p>
          <label className="mt-4 flex items-start gap-2 text-sm text-amber-950">
            <input type="checkbox" className="mt-1" checked={consent} onChange={(event) => onConsent(event.target.checked)} />
            I consent to simulate booking all selected journey legs and wallet movements.
          </label>
          <Button className="mt-4" onClick={onConfirm} disabled={!consent || loading || disabled}>
            {loading ? "Confirming" : "Confirm booking"}
          </Button>
        </div>
      </div>
    </div>
  );
}
