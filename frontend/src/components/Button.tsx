import React from "react";
import { motion, HTMLMotionProps } from "framer-motion";
import { cn } from "./utils";

interface ButtonProps extends HTMLMotionProps<"button"> {
  variant?: "primary" | "secondary" | "danger" | "ghost" | "outline";
  size?: "sm" | "md" | "lg" | "icon";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => {
    const variants = {
      primary: "bg-gradient-to-br from-emerald-500 to-emerald-700 text-white shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/40",
      secondary: "bg-white/5 border border-white/10 text-white hover:bg-white/10 hover:border-white/20",
      danger: "bg-gradient-to-br from-rose-500 to-rose-700 text-white shadow-lg shadow-rose-500/20 hover:shadow-rose-500/40",
      ghost: "bg-transparent hover:bg-white/5 text-zinc-400 hover:text-white",
      outline: "bg-transparent border border-amber-500/50 text-amber-500 hover:bg-amber-500/10 hover:border-amber-500"
    };

    const sizes = {
      sm: "h-8 px-3 text-xs",
      md: "h-10 px-4 text-sm",
      lg: "h-12 px-6 text-base",
      icon: "h-10 w-10 p-0"
    };

    return (
      <motion.button
        ref={ref}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        className={cn(
          "inline-flex items-center justify-center rounded-lg font-bold transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500/40 disabled:opacity-50 disabled:pointer-events-none",
          variants[variant],
          sizes[size],
          className
        )}
        {...props}
      />
    );
  }
);

Button.displayName = "Button";
