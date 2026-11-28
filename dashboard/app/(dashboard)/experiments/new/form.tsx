"use client";

import { useActionState, useState } from "react";

import { createExperiment, type FormState } from "@/app/actions";

type Row = { key: string; weight: string; config: string };

const INITIAL_ROWS: Row[] = [
  { key: "control", weight: "1", config: '{\n  "prompt": "You are a helpful assistant."\n}' },
  { key: "variant-b", weight: "1", config: '{\n  "prompt": "You are a concise, friendly assistant."\n}' },
];

function serialize(rows: Row[]): string {
  try {
    return JSON.stringify(
      rows.map((r) => ({ key: r.key.trim(), weight: Number(r.weight) || 1, config: JSON.parse(r.config || "{}") })),
    );
  } catch {
    return "invalid";
  }
}

export function NewExperimentForm() {
  const [rows, setRows] = useState<Row[]>(INITIAL_ROWS);
  const [state, action, pending] = useActionState<FormState, FormData>(createExperiment, { error: null });

  const update = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <form action={action} className="mt-6 space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="name">Name</label>
          <input id="name" name="name" required className="input" placeholder="Support bot prompt" />
        </div>
        <div>
          <label className="label" htmlFor="key">Key</label>
          <input
            id="key" name="key" required pattern="[a-z0-9][a-z0-9_\-]*" className="input font-mono"
            placeholder="support-prompt" title="lowercase letters, digits, - or _"
          />
        </div>
      </div>
      <div>
        <label className="label" htmlFor="description">Description <span className="text-muted">(optional)</span></label>
        <textarea id="description" name="description" rows={2} className="input" placeholder="What are you testing and why?" />
      </div>
      <div>
        <label className="label" htmlFor="primary_metric">Primary metric <span className="text-muted">(optional)</span></label>
        <input id="primary_metric" name="primary_metric" className="input font-mono" placeholder="thumbs_up" />
        <p className="mt-1 text-xs text-muted">
          The metric that decides the winner, e.g. thumbs_up. <code>dkm.trace()</code> also records latency_ms and error automatically.
        </p>
      </div>

      <div>
        <div className="flex items-center justify-between">
          <span className="label">Variants</span>
          <button
            type="button" className="btn"
            onClick={() => setRows((rs) => [...rs, { key: `variant-${String.fromCharCode(97 + rs.length)}`, weight: "1", config: "{}" }])}
          >
            + Add variant
          </button>
        </div>
        <div className="space-y-3">
          {rows.map((r, i) => (
            <div key={i} className="card p-3">
              <div className="flex gap-2">
                <input
                  aria-label="Variant key" value={r.key} onChange={(e) => update(i, { key: e.target.value })}
                  className="input font-mono" required
                />
                <input
                  aria-label="Weight" type="number" min="0.01" step="any" value={r.weight}
                  onChange={(e) => update(i, { weight: e.target.value })} className="input w-24" title="Traffic weight"
                />
                {rows.length > 2 && (
                  <button type="button" className="btn" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}>
                    Remove
                  </button>
                )}
              </div>
              {i === 0 && <p className="mt-1 text-xs text-muted">Control: other variants are compared against this one.</p>}
              <textarea
                aria-label="Config JSON" value={r.config} onChange={(e) => update(i, { config: e.target.value })}
                rows={4} spellCheck={false} className="input mt-2 font-mono text-xs"
              />
            </div>
          ))}
        </div>
      </div>

      <input type="hidden" name="variants" value={serialize(rows)} />
      {state.error && <p className="text-sm text-bad">{state.error}</p>}
      <button type="submit" disabled={pending} className="btn btn-primary">
        {pending ? "Creating…" : "Create experiment"}
      </button>
    </form>
  );
}
