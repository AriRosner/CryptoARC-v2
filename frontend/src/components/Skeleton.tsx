import React from "react";
import { cn } from "./utils";

export const Skeleton: React.FC<{ className?: string }> = ({ className }) => {
  return (
    <div className={cn("animate-pulse rounded-md bg-white/5", className)} />
  );
};
