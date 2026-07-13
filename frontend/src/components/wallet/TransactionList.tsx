import { format } from "date-fns";
import type { WalletTransaction } from "@/models/wallet";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/Status";
import { formatInr } from "@/lib/utils";

export function TransactionList({ transactions }: { transactions?: WalletTransaction[] }) {
  if (!transactions?.length) {
    return <EmptyState title="No transactions yet" message="Top-ups, booking debits, refunds, and reconciliation entries will appear here." />;
  }
  return (
    <div className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
      {transactions.slice().reverse().map((tx) => (
        <div key={tx.transaction_id} className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div>
            <div className="flex items-center gap-2">
              <Badge tone={tx.type === "debit" ? "red" : tx.type === "refund" ? "green" : "blue"}>{tx.type}</Badge>
              <p className="text-sm font-medium">{tx.description}</p>
            </div>
            <p className="mt-1 text-xs text-slate-500">{tx.trip_id} · {format(new Date(tx.timestamp), "MMM d, HH:mm")}</p>
          </div>
          <div className="text-right">
            <p className="font-semibold">{tx.type === "debit" ? "-" : "+"}{formatInr(tx.amount)}</p>
            <p className="text-xs text-slate-500">Balance {formatInr(tx.balance_after)}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
