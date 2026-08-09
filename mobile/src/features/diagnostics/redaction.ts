const SENSITIVE_KEY =
  /token|secret|seed|private|signature|pairing|authorization|credential|password|cipher|fingerprint|raw_?tx|logs?/i;
const PUBLIC_IDENTIFIER_KEY = /wallet|public_?key|address|mint/i;
const PATH_KEY = /path|directory|filename/i;

export function redactDiagnosticValue(
  key: string,
  value: unknown,
): unknown {
  return SENSITIVE_KEY.test(key) || PATH_KEY.test(key)
    ? "[REDACTED]"
    : value;
}

function shortIdentifier(value: string): string {
  const clean = value.trim();
  return clean.length <= 12
    ? clean
    : `${clean.slice(0, 6)}...${clean.slice(-5)}`;
}

function sensitiveString(value: string): boolean {
  const lower = value.toLowerCase();
  return (
    lower.includes("exponentpushtoken[") ||
    lower.includes("expopushtoken[") ||
    lower.includes("bearer ") ||
    lower.includes("seed phrase") ||
    lower.includes("private key") ||
    /[a-z]:\\/i.test(value) ||
    /(?:^|[\s"'])\/[a-z0-9_.-]+\//i.test(value)
  );
}

export function redactDiagnosticPayload(
  value: unknown,
  includePublicIdentifiers = false,
  depth = 0,
): unknown {
  if (depth >= 8) return "[REDACTED]";
  if (Array.isArray(value)) {
    return value
      .slice(0, 100)
      .map((item) =>
        redactDiagnosticPayload(item, includePublicIdentifiers, depth + 1),
      );
  }
  if (value && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value).slice(0, 100)) {
      if (PUBLIC_IDENTIFIER_KEY.test(key)) {
        if (includePublicIdentifiers && typeof item === "string") {
          output[key] = shortIdentifier(item);
        }
        continue;
      }
      const redacted = redactDiagnosticValue(key, item);
      output[key] =
        redacted === "[REDACTED]"
          ? redacted
          : redactDiagnosticPayload(
              redacted,
              includePublicIdentifiers,
              depth + 1,
            );
    }
    return output;
  }
  if (typeof value === "string") {
    return sensitiveString(value) ? "[REDACTED]" : value.slice(0, 1000);
  }
  return value;
}
