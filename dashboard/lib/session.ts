// Signed session tokens. Pure functions (no Next.js imports) so both proxy.ts and
// server code can use them.
//
// Token format: "<expiry unix seconds>.<hmac-sha256 hex>"
// The signing key is derived from DKM_API_KEY + DKM_DASHBOARD_PASSWORD, so changing
// the password logs everyone out, and no extra secret needs configuring.

import { createHash, createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "dkm_session";
export const SESSION_TTL_SECONDS = 7 * 24 * 60 * 60;

export function dashboardPassword(): string {
  return process.env.DKM_DASHBOARD_PASSWORD ?? "";
}

function signingKey(): Buffer {
  return createHash("sha256")
    .update(`dkm-session|${process.env.DKM_API_KEY ?? ""}|${dashboardPassword()}`)
    .digest();
}

function sign(payload: string): string {
  return createHmac("sha256", signingKey()).update(payload).digest("hex");
}

function safeEqual(a: string, b: string): boolean {
  // Hash first so lengths always match and timing doesn't leak length.
  const ha = createHash("sha256").update(a).digest();
  const hb = createHash("sha256").update(b).digest();
  return timingSafeEqual(ha, hb);
}

export function createToken(now = Date.now()): string {
  const expiry = String(Math.floor(now / 1000) + SESSION_TTL_SECONDS);
  return `${expiry}.${sign(expiry)}`;
}

export function verifyToken(token: string | undefined, now = Date.now()): boolean {
  if (!token || !dashboardPassword()) return false; // fail closed when no password is configured
  const [expiry, signature] = token.split(".");
  if (!expiry || !signature || !/^\d+$/.test(expiry)) return false;
  if (Number(expiry) * 1000 < now) return false;
  return safeEqual(signature, sign(expiry));
}

export function checkPassword(input: string): boolean {
  const expected = dashboardPassword();
  return expected.length > 0 && safeEqual(input, expected);
}

/** Only allow same-site relative redirects after login. */
export function safeNext(next: string | null | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}
