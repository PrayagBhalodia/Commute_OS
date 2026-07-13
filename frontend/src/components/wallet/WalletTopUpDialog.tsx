"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function WalletTopUpDialog({ onTopUp, loading }: { onTopUp: (amount: number) => void; loading?: boolean }) {
  const [amount, setAmount] = useState(10000);
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <label className="text-sm font-medium" htmlFor="topup">Top-up amount</label>
      <div className="mt-2 flex gap-2">
        <Input id="topup" type="number" min={1} value={amount} onChange={(event) => setAmount(Number(event.target.value))} />
        <Button onClick={() => onTopUp(amount)} disabled={loading || amount <= 0}>
          <Plus className="h-4 w-4" /> Top up
        </Button>
      </div>
      <p className="mt-2 text-xs text-slate-500">Simulated payment only. No real money moves.</p>
    </div>
  );
}
