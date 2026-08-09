import { router, useLocalSearchParams } from "expo-router";
import React from "react";

import { PositionDetailScreen } from "@/src/features/positions/PositionDetailScreen";

export default function PositionRoute() {
  const params = useLocalSearchParams<{ positionId?: string | string[] }>();
  const rawPositionId = Array.isArray(params.positionId) ? params.positionId[0] : params.positionId;
  const positionId = rawPositionId ? decodeURIComponent(rawPositionId) : "";
  return <PositionDetailScreen positionId={positionId} onBack={() => router.back()} />;
}
