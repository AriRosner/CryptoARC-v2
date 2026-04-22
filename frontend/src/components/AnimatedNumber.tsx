import React from "react";

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
  return <span className={className}>{`${prefix}${value.toFixed(precision)}${suffix}`}</span>;
});
