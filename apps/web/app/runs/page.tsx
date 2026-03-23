"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { fetchRuns } from "@/lib/api";

export default function RunsPage() {
  const runsQuery = useQuery({
    queryKey: ["runs-page"],
    queryFn: () => fetchRuns({ limit: 20, sort: "timestamp", order: "desc" }),
  });

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
          <div className="grid grid-cols-[1.6fr_1fr_1fr_1fr_1fr] gap-3 px-4 text-xs uppercase tracking-[0.24em] text-slate-500">
            <span>Parcel</span>
            <span>Units</span>
            <span>Profit</span>
            <span>ROI</span>
            <span>Timestamp</span>
          </div>
          <div className="mt-4 space-y-3">
            {(runsQuery.data ?? []).map((run) => (
              <Link
                key={run.run_id}
                href={`/runs/${run.run_id}`}
                className="grid grid-cols-[1.6fr_1fr_1fr_1fr_1fr] gap-3 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4 text-sm text-slate-300 transition hover:border-slate-600"
              >
                <span className="font-semibold text-slate-100">{run.parcel_id ?? "—"}</span>
                <span>{run.units ?? "—"}</span>
                <span>{formatCurrency(run.projected_profit)}</span>
                <span>{formatPercent(run.ROI)}</span>
                <span>{formatTimestamp(run.timestamp)}</span>
              </Link>
            ))}
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
