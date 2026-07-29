import React from "react";

import {
  GuardedTreasuryAction,
  type GuardedTreasuryActionProps,
} from "./WithdrawalScreen";

export function RentRecoverySheet(props: GuardedTreasuryActionProps) {
  return <GuardedTreasuryAction {...props} />;
}
