import React, { useEffect, useRef, useState } from "react";
import { motion, useSpring, useTransform } from "framer-motion";

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
  const spring = useSpring(value, {
    stiffness: 100,
    damping: 30,
    restDelta: 0.001
  });

  useEffect(() => {
    spring.set(value);
  }, [value, spring]);

  const display = useTransform(spring, (current) => {
    return `${prefix}${current.toFixed(precision)}${suffix}`;
  });

  return (
    <motion.span className={className}>
      {display}
    </motion.span>
  );
});
