import React from "react";
import { motion, HTMLMotionProps, useReducedMotion } from "framer-motion";
import { cn } from "./utils";

interface CardProps extends HTMLMotionProps<"div"> {
  glass?: boolean;
  hover?: boolean;
  appear?: boolean;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, glass = true, hover = true, appear = false, children, ...props }, ref) => {
    const shouldReduceMotion = useReducedMotion();
    const animateAppear = appear && !shouldReduceMotion;
    return (
      <motion.div
        ref={ref}
        initial={animateAppear ? { opacity: 0, y: 20 } : false}
        animate={animateAppear ? { opacity: 1, y: 0 } : undefined}
        transition={animateAppear ? { type: "spring", stiffness: 360, damping: 30 } : undefined}
        whileHover={hover && !shouldReduceMotion ? { y: -4, transition: { duration: 0.2 } } : undefined}
        className={cn(
          "relative overflow-hidden rounded-xl border border-white/10 bg-[#11131e]",
          glass && "backdrop-blur-xl bg-opacity-70",
          hover && "hover:border-white/20 hover:shadow-2xl hover:shadow-black/40",
          className
        )}
        {...props}
      >
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
        {children as React.ReactNode}
      </motion.div>
    );
  }
);

Card.displayName = "Card";
