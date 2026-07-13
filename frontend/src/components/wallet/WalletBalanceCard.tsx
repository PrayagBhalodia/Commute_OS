import { WalletCards } from "lucide-react";
import type { WalletState } from "@/models/wallet";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatInr } from "@/lib/utils";

export function WalletBalanceCard({ wallet }: { wallet?: WalletState }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><WalletCards className="h-4 w-4" /> Journey Account</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-semibold">{formatInr(wallet?.balance ?? 0)}</p>
        <p className="mt-1 text-sm text-slate-500">Unified simulated balance for booking legs and reroutes.</p>
      </CardContent>
    </Card>
  );
}
