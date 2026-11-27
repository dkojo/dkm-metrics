import Link from "next/link";

import { ErrorBox, StatusBadge } from "@/components/ui";
import { api, ApiError, type Experiment } from "@/lib/api";

export default async function Home() {
  let experiments: Experiment[];
  try {
    experiments = await api<Experiment[]>("/api/experiments");
  } catch (e) {
    return <ErrorBox message={e instanceof ApiError ? e.message : String(e)} />;
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Experiments</h1>
      <p className="mt-1 text-sm text-muted">
        Test prompts, models, parameters or any config in your LLM app.
      </p>

      {experiments.length === 0 ? (
        <div className="card mt-6 p-10 text-center">
          <p className="font-medium">No experiments yet</p>
          <p className="mt-1 text-sm text-muted">
            Create one, start it, and use the SDK to serve variants.
          </p>
          <Link href="/experiments/new" className="btn btn-primary mt-4">
            Create your first experiment
          </Link>
        </div>
      ) : (
        <div className="card mt-6 divide-y divide-border">
          {experiments.map((e) => (
            <Link
              key={e.key}
              href={`/experiments/${e.key}`}
              className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-bg"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{e.name}</span>
                  <StatusBadge status={e.status} />
                </div>
                <p className="mt-0.5 truncate font-mono text-xs text-muted">
                  {e.key} · {e.variants.map((v) => v.key).join(" vs ")}
                </p>
              </div>
              <div className="shrink-0 text-right text-sm text-muted">
                {e.event_count.toLocaleString()} events
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
