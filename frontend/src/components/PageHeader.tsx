import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "./utils";

interface PageHeaderProps {
  title: string;
  description?: string;
  children?: React.ReactNode;
  className?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  children,
  className
}) => {
  const shouldReduceMotion = useReducedMotion();
  return (
    <motion.header
      initial={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: "spring", stiffness: 340, damping: 30 }}
      className={cn(
        "relative mb-6 flex flex-col items-stretch justify-between gap-4 rounded-2xl border border-white/10 bg-[#10121c] p-5 shadow-2xl lg:mb-8 lg:flex-row lg:items-center lg:p-8",
        className
      )}
    >
      <div className="absolute inset-0 pointer-events-none bg-gradient-to-br from-emerald-500/5 to-transparent" />
      <div className="min-w-0">
        <h2 className="text-2xl font-extrabold tracking-tight text-white lg:text-3xl">{title}</h2>
        {description && (
          <p className="mt-2 text-sm font-medium text-zinc-400">{description}</p>
        )}
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-3">
        {children}
      </div>
    </motion.header>
  );
};
