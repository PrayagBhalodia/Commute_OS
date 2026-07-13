"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { WalletBalanceCard } from "@/components/wallet/WalletBalanceCard";
import { WalletTopUpDialog } from "@/components/wallet/WalletTopUpDialog";
import { TransactionList } from "@/components/wallet/TransactionList";
import { useWalletController } from "@/controllers/wallet-controller";
import { useJourneyStore } from "@/store/journey-store";

export default function WalletPage() {
  const userId = useJourneyStore((state) => state.userId);
  const wallet = useWalletController(userId);
  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <aside className="space-y-4">
        <WalletBalanceCard wallet={wallet.balanceQuery.data} />
        <WalletTopUpDialog loading={wallet.topUpMutation.isPending} onTopUp={(amount) => wallet.topUpMutation.mutate({ amount, trip_id: "wallet", description: "Wallet top-up" })} />
        <Card>
          <CardHeader><CardTitle>Reconciliation</CardTitle></CardHeader>
          <CardContent className="text-sm text-slate-600">Refunds and extra reroute costs are written to the same append-only ledger.</CardContent>
        </Card>
      </aside>
      <section className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold">Journey Account</h1>
          <p className="text-sm text-slate-500">Simulated payment wallet for top-ups, booking debits, refunds, and disruption reconciliation.</p>
        </div>
        <TransactionList transactions={wallet.ledgerQuery.data} />
      </section>
    </div>
  );
}
