import type { CSSProperties, ReactNode } from "react";

export const UP = "#15803d";
export const DOWN = "#b91c1c";

export function asNum(value: number | string | null | undefined): number | null {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function signedColor(
  value: number | string | null | undefined
): string | undefined {
  const parsed = asNum(value);
  if (parsed == null || parsed === 0) return undefined;
  return parsed > 0 ? UP : DOWN;
}

export function signedStyle(
  value: number | string | null | undefined
): CSSProperties | undefined {
  const color = signedColor(value);
  return color ? { color, fontWeight: 600 } : undefined;
}

export function SignedText({
  value,
  children,
}: {
  value: number | string | null | undefined;
  children: ReactNode;
}) {
  return <span style={signedStyle(value)}>{children}</span>;
}
