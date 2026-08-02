import { Tabs } from "expo-router";
import { BellRing, ChartNoAxesCombined, Ellipsis, Repeat2, WalletCards } from "lucide-react-native";

import { colors } from "@/src/theme";

export const FINAL_TABS = [
  ["index", "Portfolio"],
  ["trades", "Trades"],
  ["wallet", "Wallet"],
  ["alerts", "Alerts"],
  ["more", "More"],
] as const;

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.amber,
        tabBarInactiveTintColor: colors.faint,
        tabBarStyle: {
          backgroundColor: colors.panel,
          borderTopColor: colors.border,
          height: 68,
          paddingBottom: 8,
          paddingTop: 8,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: "800" },
        tabBarItemStyle: { minHeight: 48, minWidth: 52 },
      }}>
      <Tabs.Screen name="index" options={{ title: "Portfolio", tabBarIcon: ({ color }) => <ChartNoAxesCombined color={color} size={22} /> }} />
      <Tabs.Screen name="trades" options={{ title: "Trades", tabBarIcon: ({ color }) => <Repeat2 color={color} size={22} /> }} />
      <Tabs.Screen name="wallet" options={{ title: "Wallet", tabBarIcon: ({ color }) => <WalletCards color={color} size={22} /> }} />
      <Tabs.Screen name="alerts" options={{ title: "Alerts", tabBarIcon: ({ color }) => <BellRing color={color} size={22} /> }} />
      <Tabs.Screen name="more" options={{ title: "More", tabBarIcon: ({ color }) => <Ellipsis color={color} size={22} /> }} />
    </Tabs>
  );
}
