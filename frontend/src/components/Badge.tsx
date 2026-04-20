import React from "react";
import { cn } from "./utils";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "success" | "danger" | "warning" | "info" | "neutral";
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ children, variant = "neutral", className }) => {
  const variants = {
    success: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    danger: "bg-rose-500/10 text-rose-400 border-rose-500/20",
    warning: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    info: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    neutral: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20"
  };

  return (
    <span className={cn(
      "inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold border uppercase tracking-wider",
      variants[variant],
      className
    )}>
      {children}
    </span>
  );
};
