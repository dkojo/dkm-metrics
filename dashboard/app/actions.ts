"use server";

import { revalidatePath } from "next/cache";
import { redirect, unstable_rethrow } from "next/navigation";

import { api, ApiError, type Experiment } from "@/lib/api";
import { endSession, requireSession, startSession } from "@/lib/auth";
import { checkPassword, safeNext } from "@/lib/session";

// Server Actions are reachable by direct POST, so every data action checks the session
// (api() checks it too).

export type FormState = { error: string | null };

export async function login(_: FormState, form: FormData): Promise<FormState> {
  if (!checkPassword(String(form.get("password") ?? ""))) {
    await new Promise((r) => setTimeout(r, 1000)); // slow down guessing
    return { error: "Wrong password." };
  }
  await startSession();
  redirect(safeNext(String(form.get("next") ?? "/")));
}

export async function logout() {
  await endSession();
  redirect("/login");
}

export async function createExperiment(_: FormState, form: FormData): Promise<FormState> {
  await requireSession();
  let variants: unknown;
  try {
    variants = JSON.parse(String(form.get("variants") ?? "[]"));
  } catch {
    return { error: "Variant configs must be valid JSON." };
  }
  const key = String(form.get("key") ?? "").trim();
  try {
    await api<Experiment>("/api/experiments", {
      method: "POST",
      body: JSON.stringify({
        key,
        name: String(form.get("name") ?? "").trim(),
        description: String(form.get("description") ?? "").trim(),
        primary_metric: String(form.get("primary_metric") ?? "").trim() || null,
        variants,
      }),
    });
  } catch (e) {
    unstable_rethrow(e);
    return { error: e instanceof ApiError ? e.message : "Something went wrong." };
  }
  revalidatePath("/");
  redirect(`/experiments/${key}`);
}

export async function setStatus(key: string, status: Experiment["status"]) {
  await requireSession();
  await api(`/api/experiments/${encodeURIComponent(key)}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  revalidatePath("/");
  revalidatePath(`/experiments/${key}`);
}

export async function deleteExperiment(key: string) {
  await requireSession();
  await api(`/api/experiments/${encodeURIComponent(key)}`, { method: "DELETE" });
  revalidatePath("/");
  redirect("/");
}
