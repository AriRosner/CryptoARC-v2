import { Redirect } from "expo-router";

export default function CockpitRedirect() {
  return <Redirect href="/(tabs)/more?section=system" />;
}
