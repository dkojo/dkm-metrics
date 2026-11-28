import { formatValue } from "@/components/ui";
import type { Comparison, MetricResult } from "@/lib/api";

function Verdict({ c, n }: { c: Comparison; n: number }) {
  switch (c.verdict) {
    case "better":
      return <span className="font-medium text-good">Winning</span>;
    case "worse":
      return <span className="font-medium text-bad">Losing</span>;
    case "not_enough_data":
      return <span className="text-muted">Collecting data</span>;
    default: {
      const more = c.samples_needed ? Math.max(0, c.samples_needed - n) : null;
      return (
        <span className="text-muted" title="No statistically significant difference yet">
          No clear difference{more ? ` · ~${more.toLocaleString()} more needed` : ""}
        </span>
      );
    }
  }
}

function Lift({ c, lowerIsBetter }: { c: Comparison; lowerIsBetter: boolean }) {
  if (c.lift === null) return <span className="text-muted">n/a</span>;
  const good = lowerIsBetter ? c.lift < 0 : c.lift > 0;
  const color = !c.significant ? "text-muted" : good ? "text-good" : "text-bad";
  return (
    <span className={color}>
      {c.lift > 0 ? "+" : ""}
      {(c.lift * 100).toFixed(1)}%
    </span>
  );
}

/** Mean with 95% CI per variant, drawn on a shared scale. */
function CiChart({ m, control }: { m: MetricResult; control: string }) {
  const rows = m.variants.filter((v) => v.n > 0);
  if (rows.length === 0) return null;
  let lo = Math.min(...rows.map((v) => v.ci_low));
  let hi = Math.max(...rows.map((v) => v.ci_high));
  if (hi === lo) {
    lo -= 1;
    hi += 1;
  }
  const pad = (hi - lo) * 0.1;
  lo -= pad;
  hi += pad;
  const pct = (x: number) => `${((x - lo) / (hi - lo)) * 100}%`;

  return (
    <div className="space-y-2">
      {rows.map((v) => (
        <div key={v.variant} className="flex items-center gap-3">
          <span className="w-24 shrink-0 truncate font-mono text-xs text-muted">{v.variant}</span>
          <div className="relative h-4 flex-1">
            <div className="absolute inset-y-1/2 h-px w-full bg-border" />
            <div
              className={`absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full ${v.variant === control ? "bg-muted" : "bg-accent"} opacity-40`}
              style={{ left: pct(v.ci_low), width: `calc(${pct(v.ci_high)} - ${pct(v.ci_low)})` }}
            />
            <div
              className={`absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ${v.variant === control ? "bg-muted" : "bg-accent"}`}
              style={{ left: pct(v.mean) }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function MetricCard({ m, control, primary }: { m: MetricResult; control: string; primary: boolean }) {
  return (
    <section className={`card p-4 ${primary ? "border-accent" : ""}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-mono font-medium">
          {m.metric}
          {primary && <span className="ml-2 font-sans text-xs font-normal text-accent">primary</span>}
        </h3>
        <span className="text-xs text-muted">
          {m.binary ? "rate" : "mean"} · {m.lower_is_better ? "lower is better" : "higher is better"}
        </span>
      </div>

      <div className="mt-4">
        <CiChart m={m} control={control} />
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted">
            <tr className="border-b border-border">
              <th className="py-2 pr-3 font-medium">Variant</th>
              <th className="py-2 pr-3 text-right font-medium">n</th>
              <th className="py-2 pr-3 text-right font-medium">{m.binary ? "Rate" : "Mean"}</th>
              <th className="py-2 pr-3 text-right font-medium">95% CI</th>
              <th className="py-2 pr-3 text-right font-medium">vs control</th>
              <th className="py-2 pr-3 text-right font-medium">p-value</th>
              <th className="py-2 font-medium">Result</th>
            </tr>
          </thead>
          <tbody>
            {m.variants.map((v) => (
              <tr key={v.variant} className="border-b border-border last:border-0">
                <td className="py-2 pr-3 font-mono">
                  {v.variant}
                  {v.variant === control && <span className="ml-1 font-sans text-xs text-muted">(control)</span>}
                </td>
                <td className="py-2 pr-3 text-right tabular-nums">{v.n.toLocaleString()}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{v.n ? formatValue(v.mean, m.binary) : "–"}</td>
                <td className="py-2 pr-3 text-right tabular-nums text-muted">
                  {v.n > 1 ? `${formatValue(v.ci_low, m.binary)} – ${formatValue(v.ci_high, m.binary)}` : "–"}
                </td>
                <td className="py-2 pr-3 text-right tabular-nums">
                  {v.comparison ? <Lift c={v.comparison} lowerIsBetter={m.lower_is_better} /> : ""}
                </td>
                <td className="py-2 pr-3 text-right tabular-nums text-muted">
                  {v.comparison?.p_value != null
                    ? v.comparison.p_value < 0.001 ? "<0.001" : v.comparison.p_value.toFixed(3)
                    : ""}
                </td>
                <td className="py-2">{v.comparison ? <Verdict c={v.comparison} n={v.n} /> : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
