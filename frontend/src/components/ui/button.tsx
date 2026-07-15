import * as React from "react";
import { cn } from "@/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "icon";
};

export function Button({ className, variant = "primary", size = "md", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "focus-ring inline-flex items-center justify-center gap-2 rounded-md border text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "border-brand-600 bg-brand-600 text-white shadow-brand hover:bg-brand-700",
        variant === "secondary" && "border-brand-200 bg-white text-brand-700 hover:bg-brand-50",
        variant === "ghost" && "border-transparent bg-transparent text-slate-700 hover:bg-brand-50 hover:text-brand-700",
        variant === "danger" && "border-red-600 bg-red-600 text-white hover:bg-red-700",
        size === "sm" && "h-8 px-3",
        size === "md" && "h-10 px-4",
        size === "icon" && "h-10 w-10",
        className,
      )}
      {...props}
    />
  );
}
