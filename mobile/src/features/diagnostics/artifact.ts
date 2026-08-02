import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";

export const DIAGNOSTIC_EXPORT_FILENAME =
  "cryptoarc-mobile-diagnostics.json";

interface DiagnosticArtifactDependencies {
  cacheDirectory: string | null;
  write(uri: string, contents: string): Promise<void>;
  share(
    uri: string,
    options: { dialogTitle: string; mimeType: "application/json" },
  ): Promise<void>;
}

const defaultDependencies: DiagnosticArtifactDependencies = {
  cacheDirectory: FileSystem.cacheDirectory,
  write: (uri, contents) => FileSystem.writeAsStringAsync(uri, contents),
  share: (uri, options) => Sharing.shareAsync(uri, options),
};

export async function shareDiagnosticArtifact(
  payload: unknown,
  dependencies: DiagnosticArtifactDependencies = defaultDependencies,
): Promise<void> {
  if (!dependencies.cacheDirectory) {
    throw new Error("Diagnostic export storage is unavailable");
  }
  const uri = `${dependencies.cacheDirectory}${DIAGNOSTIC_EXPORT_FILENAME}`;
  await dependencies.write(uri, `${JSON.stringify(payload, null, 2)}\n`);
  await dependencies.share(uri, {
    dialogTitle: "CryptoARC redacted diagnostics",
    mimeType: "application/json",
  });
}
