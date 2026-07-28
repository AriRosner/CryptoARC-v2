import { Tabs } from "expo-router";
import {
  Bell,
  ChartNoAxesCombined,
  Gauge,
  Link2,
  ShieldAlert,
  Smartphone,
} from "lucide-react-native";

import { colors } from "@/src/theme";

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
        tabBarLabelStyle: {
          fontSize: 10,
          fontWeight: "800",
        },
        tabBarItemStyle: {
          minHeight: 48,
          minWidth: 52,
        },
      }}>
      <Tabs.Screen
        name="pairing"
        options={{
          title: "Pair",
          tabBarIcon: ({ color }) => <Link2 size={22} color={color} />,
        }}
      />
      <Tabs.Screen
        name="index"
        options={{
          title: "Portfolio",
          tabBarIcon: ({ color }) => <ChartNoAxesCombined size={22} color={color} />,
        }}
      />
      <Tabs.Screen
        name="cockpit"
        options={{
          title: "Cockpit",
          tabBarIcon: ({ color }) => <Gauge size={22} color={color} />,
        }}
      />
      <Tabs.Screen
        name="feed"
        options={{
          title: "Feed",
          tabBarIcon: ({ color }) => <Bell size={22} color={color} />,
        }}
      />
      <Tabs.Screen
        name="risk"
        options={{
          title: "Risk",
          tabBarIcon: ({ color }) => <ShieldAlert size={22} color={color} />,
        }}
      />
      <Tabs.Screen
        name="device"
        options={{
          title: "Device",
          tabBarIcon: ({ color }) => <Smartphone size={22} color={color} />,
        }}
      />
    </Tabs>
  );
}
