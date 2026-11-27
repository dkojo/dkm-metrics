import type { Experiment } from "@/lib/api";

const STATUS_STYLE: Record<Experiment["status"], string> = {
  draft: "text-muted border-border",
  running: "text-good border-good",
  stopped: "text-warn border-warn",
};

export function StatusBadge({ status }: { status: Experiment["status"] }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[status]}`}>
      {status === "running" && "● "}
      {status}
    </span>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="card border-bad p-4 text-sm">
      <p className="font-medium text-bad">Error</p>
      <p className="mt-1 text-muted">{message}</p>
    </div>
  );
}

export function formatValue(value: number, binary: boolean): string {
  if (binary) return `${(value * 100).toFixed(1)}%`;
  const abs = Math.abs(value);
  if (abs >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (abs >= 10) return value.toFixed(1);
  if (abs >= 0.01 || value === 0) return value.toFixed(3);
  return value.toPrecision(2);
}
