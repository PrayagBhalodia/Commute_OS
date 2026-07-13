import { AlertTriangle, CheckCircle2, Loader2, WifiOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function LoadingSkeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200 ${className}`} />;
}

export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
      <p className="font-medium text-slate-900">{title}</p>
      <p className="mt-2 text-sm text-slate-500">{message}</p>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <AlertTriangle className="mt-0.5 h-4 w-4" />
      <span>{message}</span>
    </div>
  );
}

export function SimulatedDataBadge() {
  return <Badge tone="amber">Simulated prototype</Badge>;
}

export function BackendStatus({ online, loading }: { online: boolean; loading?: boolean }) {
  if (loading) {
    return (
      <Badge>
        <Loader2 className="h-3 w-3 animate-spin" /> Checking backend
      </Badge>
    );
  }
  return online ? (
    <Badge tone="green">
      <CheckCircle2 className="h-3 w-3" /> Backend online
    </Badge>
  ) : (
    <Badge tone="red">
      <WifiOff className="h-3 w-3" /> Backend offline
    </Badge>
  );
}
