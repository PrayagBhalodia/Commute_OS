export interface WalletState {
  user_id: string;
  balance: number;
  currency: string;
  updated_at: string;
}

export interface WalletTransaction {
  transaction_id: string;
  trip_id: string;
  user_id: string;
  type: "topup" | "debit" | "refund" | string;
  amount: number;
  description: string;
  timestamp: string;
  balance_after: number;
  idempotency_key?: string | null;
}

export interface TopUpRequest {
  amount: number;
  trip_id: string;
  description: string;
  idempotency_key?: string | null;
}

export interface ReconciliationResult {
  trip_id: string;
  user_id: string;
  original_total: number;
  revised_total: number;
  difference: number;
  action: "refund" | "charge_more" | "top_up_required" | "no_action" | string;
  wallet_balance_after: number;
  transaction?: WalletTransaction | null;
  message: string;
}
