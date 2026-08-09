import { router, useLocalSearchParams } from "expo-router";
import React from "react";

import { TradeDetailScreen } from "@/src/features/trades/TradeDetailScreen";

export default function TradeRoute() {
  const params = useLocalSearchParams<{ intentId?: string | string[] }>();
  const rawIntentId = Array.isArray(params.intentId)
    ? params.intentId[0]
    : params.intentId;
  const intentId = rawIntentId ? decodeURIComponent(rawIntentId) : "";
  return <TradeDetailScreen intentId={intentId} onBack={() => router.back()} />;
}
