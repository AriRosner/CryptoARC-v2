import { Redirect } from "expo-router";

export default function RiskRedirect() {
  return <Redirect href="/(tabs)/more?section=system" />;
}
