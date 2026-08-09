import type { MotionPolicy } from "./policy";

export function chartTransition(policy: MotionPolicy) {
  return policy.duration.normal === 0
    ? undefined
    : { type: "timing" as const, duration: policy.duration.normal };
}

export function listTransitionDelay(policy: MotionPolicy, index: number): number {
  if (!policy.sharedTransitions) return 0;
  return Math.min(index, 8) * Math.round(policy.duration.fast / 3);
}

export function sheetAnimationConfig(policy: MotionPolicy) {
  return policy.duration.normal === 0
    ? { duration: 0 }
    : {
        damping: policy.spring.damping,
        stiffness: policy.spring.stiffness,
      };
}

export function runEmergencyAction(
  action: () => void,
  _animationCompletion?: Promise<unknown>,
): void {
  action();
}
