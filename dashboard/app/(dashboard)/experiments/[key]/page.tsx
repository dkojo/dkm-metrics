import Link from "next/link";
import { notFound, unstable_rethrow } from "next/navigation";

import { ErrorBox, StatusBadge } from "@/components/ui";
import { api, ApiError, type Experiment, type Results } from "@/lib/api";

import { AutoRefresh, Controls } from "./controls";
import { MetricCard } from "./metric-card";

export default async function ExperimentPage(props: PageProps<"/experiments/[key]">) {
  const { key } = await props.params;
  const path = `/api/experiments/${encodeURIComponent(key)}`;

  let experiment: Experiment;
  let results: Results;
  try {
    [experiment, results] = await Promise.all([api<Experiment>(path), api<Results>(`${path}/results`)]);
  } catch (e) {
    unstable_rethrow(e);
    if (e instanceof ApiError && e.status === 404) notFound();
    return <ErrorBox message={e instanceof ApiError ? e.message : String(e)} />;
  }

  const totalUsers = Object.values(results.users).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-8">
      {experiment.status === "running" && <AutoRefresh />}

      <div>
        <Link href="/" className="text-sm text-muted hover:text-fg">← Experiments</Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{experiment.name}</h1>
              <StatusBadge status={experiment.status} />
            </div>
            <p className="mt-1 font-mono text-xs text-muted">{experiment.key}</p>
            {experiment.description && <p className="mt-2 max-w-2xl text-sm text-muted">{experiment.description}</p>}
          </div>
          <Controls experiment={experiment} />
        </div>
      </div>

      {/* Variants */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-muted">Variants</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {experiment.variants.map((v, i) => {
            const totalWeight = experiment.variants.reduce((a, x) => a + x.weight, 0);
            return (
              <div key={v.key} className="card p-3">
                <div className="flex items-baseline justify-between">
                  <span className="font-mono font-medium">
                    {v.key}
                    {i === 0 && <span className="ml-1 font-sans text-xs font-normal text-muted">(control)</span>}
                  </span>
                  <span className="text-xs text-muted">
                    {Math.round((v.weight / totalWeight) * 100)}% traffic · {(results.users[v.key] ?? 0).toLocaleString()} users
                  </span>
                </div>
                <pre className="mt-2 max-h-40 overflow-auto rounded bg-bg p-2 font-mono text-xs">
                  {JSON.stringify(v.config, null, 2)}
                </pre>
              </div>
            );
          })}
        </div>
      </section>

      {/* Results */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-muted">
          Results · {totalUsers.toLocaleString()} users · {experiment.event_count.toLocaleString()} events
        </h2>
        {results.metrics.length === 0 ? (
          <div className="card p-6 text-sm text-muted">
            {experiment.status === "draft"
              ? "Start the experiment, then send events from your app with the SDK below."
              : "No events yet. Results appear here as your app sends them."}
          </div>
        ) : (
          <div className="space-y-4">
            {results.metrics.map((m) => (
              <MetricCard key={m.metric} m={m} control={results.control} primary={m.metric === results.primary_metric} />
            ))}
          </div>
        )}
      </section>

      {/* Integration snippet */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-muted">Use it in your app</h2>
        <pre className="card overflow-x-auto p-4 font-mono text-xs leading-relaxed">{`from dkm import DKM

dkm = DKM()  # reads DKM_API_KEY and DKM_BASE_URL

v = dkm.variant("${experiment.key}", user_id=user.id, default=${JSON.stringify(experiment.variants[0]?.config ?? {})})
with dkm.trace(v) as t:          # records latency_ms and error
    reply = call_llm(**v.config)
    t.record(tokens=reply.usage.total_tokens)

dkm.track(v, "${experiment.primary_metric ?? "thumbs_up"}", 1)`}</pre>
      </section>
    </div>
  );
}
