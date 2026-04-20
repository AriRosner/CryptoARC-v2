import React from "react";
import { motion } from "framer-motion";
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
  return (
    <motion.header
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      className={cn(
        "relative mb-8 flex items-center justify-between gap-4 rounded-2xl border border-white/10 bg-[#10121c] p-8 shadow-2xl",
        className
      )}
    >
      <div className="absolute inset-0 pointer-events-none bg-gradient-to-br from-emerald-500/5 to-transparent" />
      <div>
        <h2 className="text-3xl font-extrabold tracking-tight text-white">{title}</h2>
        {description && (
          <p className="mt-2 text-sm font-medium text-zinc-400">{description}</p>
        )}
      </div>
      <div className="flex items-center gap-3">
        {children}
      </div>
    </motion.header>
  );
};
