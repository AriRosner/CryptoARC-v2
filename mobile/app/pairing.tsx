import { CameraView, useCameraPermissions } from "expo-camera";
import { router } from "expo-router";
import { CheckCircle2, KeyRound, QrCode, ShieldCheck, Wifi } from "lucide-react-native";
import React, { useState } from "react";
import { ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { claimMobilePairing, normalizeApiBaseUrl, probeMobileHealth } from "@/src/api";
import { ActionButton, DetailRow, ErrorBanner, MetricTile, PageHeader, Section, StatusBadge } from "@/src/components/ui";
import { useSession } from "@/src/core/session/SessionProvider";
import { parsePairingPayload } from "@/src/security";
import { colors, spacing } from "@/src/theme";

export default function PairingScreen() {
  const session = useSession();
  const [permission, requestPermission] = useCameraPermissions();
  const [apiBaseInput, setApiBaseInput] = useState(session.apiBaseUrl);
  const [pairingId, setPairingId] = useState("");
  const [code, setCode] = useState("");
  const [deviceName, setDeviceName] = useState("Android cockpit");
  const [scanning, setScanning] = useState(false);
  const [healthOk, setHealthOk] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const pairWithManualCode = async (input: {
    apiBaseUrl: string;
    pairingId: string;
    code: string;
    deviceName: string;
  }) => {
    const generation = session.generation;
    setLoading(true);
    setError("");
    try {
      const apiBaseUrl = normalizeApiBaseUrl(input.apiBaseUrl);
      const claimed = await claimMobilePairing({
        apiBaseUrl,
        pairingId: input.pairingId,
        code: input.code,
        deviceName: input.deviceName || "Android cockpit",
        platform: "android",
      });
      if (!session.isCurrentGeneration(generation)) return false;
      return session.replaceSession(apiBaseUrl, claimed.token, claimed.device, generation);
    } catch (cause) {
      if (session.isCurrentGeneration(generation)) {
        setError(cause instanceof Error ? cause.message : "Pairing failed");
      }
      throw cause;
    } finally {
      if (session.isCurrentGeneration(generation)) setLoading(false);
    }
  };

  const pairWithQrPayload = async (payload: string) => {
    const parsed = parsePairingPayload(payload);
    return pairWithManualCode({
      apiBaseUrl: parsed.apiBaseUrl || apiBaseInput,
      pairingId: parsed.pairingId,
      code: parsed.code,
      deviceName,
    });
  };

  const submitManual = async () => {
    try {
      if (await pairWithManualCode({ apiBaseUrl: apiBaseInput, pairingId, code, deviceName })) {
        router.replace("/");
      }
    } catch {}
  };

  const submitHealth = async () => {
    try {
      await probeMobileHealth(apiBaseInput);
      setHealthOk(true);
    } catch {
      setHealthOk(false);
    }
  };

  const openScanner = async () => {
    setError("");
    if (!permission?.granted) {
      const result = await requestPermission();
      if (!result.granted) {
        setError("Camera permission is required to scan pairing QR codes.");
        return;
      }
    }
    setScanning(true);
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader
          eyebrow="Private tunnel pairing"
          title="Pair Device"
          subtitle="Connect this phone to the revocable mobile cockpit token from desktop Settings."
          right={<StatusBadge label={session.token ? "Paired" : "Setup"} tone={session.token ? "success" : "warning"} />}
        />
        <ErrorBanner message={error} />

        {session.token ? (
          <Section title="Current Device" right={<StatusBadge label="Paired" tone="success" />}>
            <View style={styles.metricGrid}>
              <MetricTile label="Device" value={session.device?.name || "Mobile"} detail="secure token" />
              <MetricTile label="Scopes" value={(session.device?.scopes ?? []).length || 0} detail="revocable" />
            </View>
            <DetailRow label="API URL" value={session.apiBaseUrl} tone="info" />
          </Section>
        ) : null}

        <Section title="Setup Path" right={<ShieldCheck size={16} color={healthOk ? colors.emerald : colors.amber} />}>
          <View style={styles.stepGrid}>
            <View style={[styles.step, healthOk && styles.stepDone]}>
              <Text style={styles.stepNumber}>1</Text>
              <Text style={styles.stepLabel}>Tunnel</Text>
            </View>
            <View style={[styles.step, session.token && styles.stepDone]}>
              <Text style={styles.stepNumber}>2</Text>
              <Text style={styles.stepLabel}>Pair</Text>
            </View>
            <View style={[styles.step, session.token && styles.stepDone]}>
              <Text style={styles.stepNumber}>3</Text>
              <Text style={styles.stepLabel}>Cockpit</Text>
            </View>
          </View>
        </Section>

        <Section title="Tunnel" right={<StatusBadge label={healthOk ? "Reachable" : "Unchecked"} tone={healthOk ? "success" : "warning"} />}>
          <TextInput
            value={apiBaseInput}
            onChangeText={setApiBaseInput}
            placeholder="https://cryptoarc-node.tailnet.ts.net"
            placeholderTextColor={colors.faint}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            style={styles.input}
          />
          <ActionButton
            label={healthOk ? "Tunnel OK" : "Check Tunnel"}
            onPress={() => void submitHealth()}
            loading={loading}
            icon={healthOk ? <CheckCircle2 size={16} color={colors.text} /> : <Wifi size={16} color={colors.text} />}
          />
        </Section>

        <Section title="QR Scan" right={<QrCode size={16} color={colors.amber} />}>
          {scanning ? (
            <View style={styles.cameraShell}>
              <CameraView
                style={styles.camera}
                barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
                onBarcodeScanned={({ data }) => {
                  setScanning(false);
                  void pairWithQrPayload(String(data))
                    .then((paired) => {
                      if (paired) router.replace("/");
                    })
                    .catch(() => setScanning(false));
                }}
              />
            </View>
          ) : (
            <ActionButton label="Scan QR" tone="primary" onPress={() => void openScanner()} icon={<QrCode size={16} color={colors.text} />} />
          )}
        </Section>

        <Section title="Manual Code" right={<KeyRound size={16} color={colors.amber} />}>
          <TextInput value={deviceName} onChangeText={setDeviceName} placeholder="Device name" placeholderTextColor={colors.faint} style={styles.input} />
          <TextInput
            value={pairingId}
            onChangeText={setPairingId}
            placeholder="Pairing ID"
            placeholderTextColor={colors.faint}
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
          />
          <TextInput
            value={code}
            onChangeText={setCode}
            placeholder="Manual code"
            placeholderTextColor={colors.faint}
            keyboardType="number-pad"
            style={styles.input}
          />
          <ActionButton label="Claim Pairing" tone="primary" onPress={() => void submitManual()} disabled={loading || !apiBaseInput || !pairingId || !code} loading={loading} />
        </Section>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    padding: spacing.lg,
    gap: spacing.md,
  },
  metricGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  stepGrid: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  step: {
    flex: 1,
    minHeight: 74,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    backgroundColor: colors.deep,
    padding: spacing.sm,
    justifyContent: "space-between",
  },
  stepDone: {
    borderColor: colors.emerald,
    backgroundColor: colors.emeraldSoft,
  },
  stepNumber: {
    color: colors.amber,
    fontSize: 18,
    fontWeight: "900",
  },
  stepLabel: {
    color: colors.text,
    fontSize: 11,
    fontWeight: "900",
    textTransform: "uppercase",
  },
  input: {
    minHeight: 46,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: 8,
    backgroundColor: colors.black,
    color: colors.text,
    fontSize: 13,
    paddingHorizontal: spacing.md,
  },
  cameraShell: {
    overflow: "hidden",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    height: 280,
  },
  camera: {
    flex: 1,
  },
});
