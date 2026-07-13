import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatInr(value?: number | null) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value ?? 0);
}

export function formatMinutes(value?: number | null) {
  const minutes = Math.max(0, Math.round(value ?? 0));
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (!hours) return `${mins} min`;
  return `${hours}h ${mins}m`;
}

export function pct(value?: number | null) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

export function apiErrorMessage(error: unknown) {
  if (typeof error === "object" && error && "message" in error) {
    return String(error.message);
  }
  return "Something went wrong.";
}
