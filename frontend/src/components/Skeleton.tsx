import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "./utils";

export const Skeleton: React.FC<{ className?: string }> = ({ className }) => {
  const shouldReduceMotion = useReducedMotion();
  return (
    <motion.div
      aria-hidden="true"
      initial={shouldReduceMotion ? false : { opacity: 0.72 }}
      animate={{ opacity: 1 }}
      transition={{ duration: shouldReduceMotion ? 0.01 : 0.24, ease: [0.2, 0.82, 0.2, 1] }}
      className={cn(
        "group/skeleton relative overflow-hidden rounded-md border border-white/6 bg-[linear-gradient(110deg,rgba(255,255,255,0.045),rgba(255,255,255,0.018)_42%,rgba(255,255,255,0.035))] shadow-[inset_0_1px_0_rgba(255,255,255,0.035)]",
        className
      )}
    >
      {!shouldReduceMotion ? (
        <motion.div
          className="absolute inset-y-0 -left-2/3 w-2/3 bg-[linear-gradient(105deg,transparent,rgba(255,255,255,0.055)_38%,rgba(232,154,74,0.075)_50%,rgba(255,255,255,0.05)_62%,transparent)] blur-[1px]"
          animate={{ x: ["0%", "260%"] }}
          transition={{ duration: 2.6, repeat: Number.POSITIVE_INFINITY, ease: [0.33, 1, 0.68, 1], repeatDelay: 0.35 }}
        />
      ) : null}
      <div className="absolute inset-0 bg-gradient-to-b from-white/[0.035] via-transparent to-black/10" />
    </motion.div>
  );
};
