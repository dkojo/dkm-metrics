// Server-side client for the dkm-metrics API: the dashboard's data-access layer.
// Only import from Server Components / Actions: it reads the API key from the environment,
// which never reaches the browser, and checks the dashboard session before every call.

import { requireSession } from "./auth";

export type Variant = { key: string; weight: number; config: Record<string, unknown> };

export type Experiment = {
  key: string;
  name: string;
  description: string;
  status: "draft" | "running" | "stopped";
  primary_metric: string | null;
  created_at: string;
  variants: Variant[];
  event_count: number;
};

export type Comparison = {
  test: "proportion" | "welch_t";
  lift: number | null;
  diff: number;
  p_value: number | null;
  significant: boolean;
  verdict: "better" | "worse" | "no_difference" | "not_enough_data";
  samples_needed: number | null;
};

export type VariantStats = {
  variant: string;
  n: number;
  mean: number;
  std: number;
  ci_low: number;
  ci_high: number;
  comparison?: Comparison;
};

export type MetricResult = {
  metric: string;
  lower_is_better: boolean;
  binary: boolean;
  variants: VariantStats[];
};

export type Results = {
  experiment: string;
  status: string;
  control: string;
  primary_metric: string | null;
  users: Record<string, number>;
  metrics: MetricResult[];
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export const API_URL = process.env.DKM_API_URL ?? "http://localhost:8000";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  await requireSession(); // redirects to /login if signed out
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        Authorization: `Bearer ${process.env.DKM_API_KEY ?? ""}`,
        "Content-Type": "application/json",
        ...init.headers,
      },
    });
  } catch {
    throw new ApiError(0, `Can't reach the dkm-metrics server at ${API_URL}. Is it running?`);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, formatDetail(body?.detail) ?? `${res.status} ${res.statusText}`);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

// FastAPI returns either a string or a list of validation errors.
function formatDetail(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) =>
        [d.loc?.filter((x) => x !== "body").join("."), d.msg].filter(Boolean).join(": "),
      )
      .join("; ");
  }
  return JSON.stringify(detail);
}
