"use client";

import Link from "next/link";
import { useQueries, useQuery } from "@tanstack/react-query";

import { fetchRun, fetchRuns } from "@/lib/api";
import { pipelineRunStateLabel, type PipelineRun } from "@/lib/parcels";

export default function RunsPage() {
  const runsQuery = useQuery({
    queryKey: ["runs-page"],
    queryFn: () => fetchRuns({ limit: 20, sort: "timestamp", order: "desc" }),
  });
  const runDetailQueries = useQueries({
    queries: (runsQuery.data ?? []).map((summary) => ({
      queryKey: ["runs-page-detail", summary.run_id],
      queryFn: () => fetchRun(summary.run_id),
      retry: false,
    })),
  });
  const runsById = new Map(
    runDetailQueries
      .map((query) => query.data)
      .filter((run): run is PipelineRun => Boolean(run))
      .map((run) => [run.run_id, run])
  );

  return (
    <div className="px-6 py-8">
      <div className="mx-auto max-w-[1400px]">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.32em] text-slate-500">Saved runs</div>
            <h1 className="mt-2 text-3xl font-semibold text-slate-100">
              Bedrock feasibility history and saved pipeline runs
            </h1>
          </div>
          <Link
            href="/map"
            className="rounded-2xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
          >
            Open parcel map
          </Link>
        </div>

        <div className="mt-8 rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
          <div className="grid grid-cols-[1.5fr_1fr_1fr_1fr_1fr_1fr] gap-3 px-4 text-xs uppercase tracking-[0.24em] text-slate-500">
            <span>Parcel</span>
            <span>Status</span>
            <span>Units</span>
            <span>Profit</span>
            <span>ROI</span>
            <span>Timestamp</span>
          </div>
          <div className="mt-4 space-y-3">
            {(runsQuery.data ?? []).map((summary) => {
              const run = runsById.get(summary.run_id);
              return (
                <Link
                  key={summary.run_id}
                  href={`/runs/${summary.run_id}`}
                  className="grid grid-cols-[1.5fr_1fr_1fr_1fr_1fr_1fr] gap-3 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4 text-sm text-slate-300 transition hover:border-slate-600"
                >
                  <span className="font-semibold text-slate-100">{summary.parcel_id ?? "—"}</span>
                  <RunStateBadge run={run} />
                  <span>{summary.units ?? "—"}</span>
                  <span>{formatCurrency(summary.projected_profit)}</span>
                  <span>{formatPercent(summary.ROI)}</span>
                  <span>{formatTimestamp(summary.timestamp)}</span>
                </Link>
              );
            })}
            {!runsQuery.data?.length ? (
              <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-8 text-sm text-slate-500">
                No Bedrock pipeline runs saved yet. Open Studio and execute the pipeline to seed history.
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function RunStateBadge({ run }: { run?: PipelineRun | null }) {
  if (!run) {
    return <span className="text-xs text-slate-500">Loading…</span>;
  }
  const tone =
    run.status === "completed"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
      : run.status === "non_buildable"
        ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
        : "border-rose-400/40 bg-rose-400/10 text-rose-300";
  return (
    <span className={`inline-flex w-fit rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${tone}`}>
      {pipelineRunStateLabel(run)}
    </span>
  );
}

function formatCurrency(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function formatPercent(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatTimestamp(value: string) {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return value;
  return timestamp.toLocaleString();
}
