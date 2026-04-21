import React from "react";
import { motion } from "framer-motion";
import { cn } from "./utils";

export const Skeleton: React.FC<{ className?: string }> = ({ className }) => {
  return (
    <motion.div
      aria-hidden="true"
      initial={{ opacity: 0.72 }}
      animate={{ opacity: [0.72, 1, 0.78] }}
      transition={{ duration: 1.8, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
      className={cn(
        "relative overflow-hidden rounded-md border border-white/8 bg-[#0d1018]/85 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]",
        className
      )}
    >
      <motion.div
        className="absolute inset-y-0 -left-1/3 w-1/3 bg-gradient-to-r from-transparent via-[#00ffbd]/12 to-transparent blur-md"
        animate={{ x: ["-25%", "340%"] }}
        transition={{ duration: 1.6, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
      />
      <div className="absolute inset-0 bg-gradient-to-br from-white/6 via-transparent to-[#8b5cf6]/8" />
    </motion.div>
  );
};
