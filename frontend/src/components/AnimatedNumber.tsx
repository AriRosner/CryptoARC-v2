import React from "react";
import { animate, useMotionValue, useReducedMotion } from "framer-motion";

interface AnimatedNumberProps {
  value: number;
  precision?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}

export const AnimatedNumber: React.FC<AnimatedNumberProps> = React.memo(({
  value,
  precision = 2,
  prefix = "",
  suffix = "",
  className
}) => {
  const shouldReduceMotion = useReducedMotion();
  const motionValue = useMotionValue(value);
  const [displayValue, setDisplayValue] = React.useState(value);
  const safeValue = Number.isFinite(value) ? value : 0;
  const safeDisplayValue = Number.isFinite(displayValue) ? displayValue : safeValue;

  React.useEffect(() => {
    return motionValue.on("change", (latest) => setDisplayValue(latest));
  }, [motionValue]);

  React.useEffect(() => {
    if (shouldReduceMotion) {
      // Honor prefers reduced motion by updating immediately instead of rolling.
      motionValue.set(safeValue);
      setDisplayValue(safeValue);
      return undefined;
    }

    const controls = animate(motionValue, safeValue, {
      duration: 0.55,
      ease: "easeOut"
    });

    return controls.stop;
  }, [motionValue, safeValue, shouldReduceMotion]);

  return <span className={className}>{`${prefix}${safeDisplayValue.toFixed(precision)}${suffix}`}</span>;
});
