import React from "react";

import {
  GuardedTreasuryAction,
  type GuardedTreasuryActionProps,
} from "./WithdrawalScreen";

export function ProfitSweepSheet(props: GuardedTreasuryActionProps) {
  return <GuardedTreasuryAction {...props} />;
}
