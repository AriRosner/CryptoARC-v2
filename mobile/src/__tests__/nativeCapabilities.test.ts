import app from "../../app.json";
import firebase from "../../google-services.json";
import pkg from "../../package.json";

test("command center native capabilities are pinned and configured", () => {
  expect(pkg.dependencies).toEqual(
    expect.objectContaining({
      "@gorhom/bottom-sheet": expect.any(String),
      "@react-native-community/netinfo": expect.any(String),
      "@tanstack/react-query": expect.any(String),
      "expo-haptics": expect.any(String),
      "expo-notifications": expect.any(String),
      "expo-sqlite": expect.any(String),
      "react-native-gesture-handler": expect.any(String),
      "victory-native": expect.any(String),
      zustand: expect.any(String),
    }),
  );
  expect(app.expo.plugins).toEqual(
    expect.arrayContaining([
      expect.arrayContaining(["expo-notifications"]),
      expect.arrayContaining(["expo-sqlite"]),
    ]),
  );
});

test("Android push client configuration targets the release package", () => {
  expect(
    (app.expo.android as { googleServicesFile?: string }).googleServicesFile,
  ).toBe("./google-services.json");

  const packages = firebase.client.map(
    (client) => client.client_info.android_client_info.package_name,
  );
  expect(packages).toContain("com.cryptoarc.cockpit");
});
