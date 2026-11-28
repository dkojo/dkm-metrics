// Session helpers for Server Components and Server Actions.

import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";

import { createToken, SESSION_COOKIE, SESSION_TTL_SECONDS, verifyToken } from "./session";

export async function isAuthenticated(): Promise<boolean> {
  await connection(); // per-request: never prerender a session check (it reads the clock)
  const store = await cookies();
  return verifyToken(store.get(SESSION_COOKIE)?.value);
}

/** Call at the start of anything that reads or changes data. */
export async function requireSession(): Promise<void> {
  if (!(await isAuthenticated())) redirect("/login");
}

export async function startSession(): Promise<void> {
  const h = await headers();
  const https = h.get("x-forwarded-proto") === "https" || process.env.DKM_SECURE_COOKIES === "true";
  (await cookies()).set(SESSION_COOKIE, createToken(), {
    httpOnly: true,
    sameSite: "lax",
    secure: https,
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
}

export async function endSession(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}
