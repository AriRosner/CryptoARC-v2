import React from "react";
import { motion, HTMLMotionProps } from "framer-motion";
import { cn } from "./utils";

interface CardProps extends HTMLMotionProps<"div"> {
  glass?: boolean;
  hover?: boolean;
  appear?: boolean;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, glass = true, hover = true, appear = false, children, ...props }, ref) => {
    return (
      <motion.div
        ref={ref}
        initial={appear ? { opacity: 0, y: 20 } : false}
        animate={appear ? { opacity: 1, y: 0 } : undefined}
        transition={appear ? { duration: 0.4, ease: [0.2, 0.8, 0.2, 1] } : undefined}
        whileHover={hover ? { y: -4, transition: { duration: 0.2 } } : undefined}
        className={cn(
          "relative overflow-hidden rounded-xl border border-white/10 bg-[#11131e]",
          glass && "backdrop-blur-xl bg-opacity-70",
          hover && "hover:border-white/20 hover:shadow-2xl hover:shadow-black/40",
          className
        )}
        {...props}
      >
        <div className="absolute inset-0 pointer-events-none bg-gradient-to-br from-white/5 to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
        {children as React.ReactNode}
      </motion.div>
    );
  }
);

Card.displayName = "Card";
