"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api, ApiError, type Experiment } from "@/lib/api";

// Note: the dashboard has no login in v1. Run it on a trusted network (see README).

export type FormState = { error: string | null };

export async function createExperiment(_: FormState, form: FormData): Promise<FormState> {
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
    return { error: e instanceof ApiError ? e.message : "Something went wrong." };
  }
  revalidatePath("/");
  redirect(`/experiments/${key}`);
}

export async function setStatus(key: string, status: Experiment["status"]) {
  await api(`/api/experiments/${encodeURIComponent(key)}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  revalidatePath("/");
  revalidatePath(`/experiments/${key}`);
}

export async function deleteExperiment(key: string) {
  await api(`/api/experiments/${encodeURIComponent(key)}`, { method: "DELETE" });
  revalidatePath("/");
  redirect("/");
}
