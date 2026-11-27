"use client";

import { useRouter } from "next/navigation";
import { useEffect, useTransition } from "react";

import { deleteExperiment, setStatus } from "@/app/actions";
import type { Experiment } from "@/lib/api";

export function Controls({ experiment }: { experiment: Experiment }) {
  const [pending, start] = useTransition();
  const { key, status } = experiment;

  return (
    <div className="flex gap-2">
      {status !== "running" && (
        <button className="btn btn-primary" disabled={pending} onClick={() => start(() => setStatus(key, "running"))}>
          {status === "draft" ? "Start" : "Resume"}
        </button>
      )}
      {status === "running" && (
        <button className="btn" disabled={pending} onClick={() => start(() => setStatus(key, "stopped"))}>
          Stop
        </button>
      )}
      <button
        className="btn text-bad"
        disabled={pending}
        onClick={() => {
          if (confirm(`Delete "${experiment.name}" and all its data? This can't be undone.`)) {
            start(() => deleteExperiment(key));
          }
        }}
      >
        Delete
      </button>
    </div>
  );
}

/** Re-fetches server data every few seconds while an experiment is running. */
export function AutoRefresh({ seconds = 10 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const id = setInterval(() => router.refresh(), seconds * 1000);
    return () => clearInterval(id);
  }, [router, seconds]);
  return null;
}
