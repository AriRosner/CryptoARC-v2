import { Redirect } from "expo-router";

export default function DeviceRedirect() {
  return <Redirect href="/(tabs)/more?section=device" />;
}
