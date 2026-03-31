"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchRun, fetchRuns } from "@/lib/api";
import { buildParcelMemory } from "@/lib/runMemory";

export default function RunsPage() {
  const runsQuery = useQuery({
    queryKey: ["runs-memory-index"],
    queryFn: async () => {
      const summaries = await fetchRuns({ limit: 48, sort: "timestamp", order: "desc" });
      const details = await Promise.all(
        summaries
          .filter((summary) => summary.parcel_id)
          .map((summary) => fetchRun(summary.run_id))
      );
      return details;
    },
    retry: false,
  });

  const parcelMemories = useMemo(() => {
    const grouped = new Map<string, ReturnType<typeof buildParcelMemory>>();
    for (const run of runsQuery.data ?? []) {
      const parcelId = run.parcel_id;
      if (!parcelId) continue;
      const existingRuns = grouped.get(parcelId)?.runs ?? [];
      grouped.set(parcelId, buildParcelMemory([...existingRuns, run]));
    }
    return Array.from(grouped.values())
      .filter((memory): memory is NonNullable<typeof memory> => Boolean(memory))
      .sort((left, right) => Date.parse(right.lastUpdatedAt) - Date.parse(left.lastUpdatedAt));
  }, [runsQuery.data]);

  return (
    <div className="min-h-[calc(100vh-72px)] bg-slate-950 px-6 py-8 text-slate-100">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.32em] text-slate-500">Decision memory</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight">Parcel run memory</h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
              This view is parcel-centric. It shows what the system currently thinks about each parcel,
              what it thought before, and how that recommendation changed.
            </p>
          </div>
          <Link
            href="/opportunities"
            className="inline-flex rounded-2xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
          >
            Back to opportunities
          </Link>
        </div>

        {runsQuery.isLoading ? (
          <EmptyState copy="Loading parcel memory from saved pipeline runs..." />
        ) : runsQuery.isError ? (
          <EmptyState copy={runsQuery.error instanceof Error ? runsQuery.error.message : "Run memory failed to load."} />
        ) : parcelMemories.length ? (
          <div className="grid gap-4">
            {parcelMemories.map((memory) => (
              <article
                key={memory.parcel_id}
                className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-5"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="font-mono text-sm text-slate-300">{memory.parcel_id}</span>
                      <StatusPill status={memory.latest.status} />
                    </div>
                    <p className="mt-3 text-lg font-semibold text-slate-100">{memory.latest.jurisdiction}</p>
                    <p className="mt-2 text-sm leading-6 text-slate-400">
                      Latest saved feasibility result for this parcel.
                    </p>
                  </div>
                  <div className="grid gap-2 text-sm text-slate-300">
                    <div>
                      <span className="text-slate-500">Last updated:</span> {formatTimestamp(memory.lastUpdatedAt)}
                    </div>
                    <div>
                      <span className="text-slate-500">Current deal status:</span> {memory.latest.status}
                    </div>
                    <div>
                      <span className="text-slate-500">Previous deal status:</span>{" "}
                      {memory.previous?.status ?? "No prior saved result"}
                    </div>
                    <div>
                      <span className="text-slate-500">Saved runs:</span> {memory.runCount}
                    </div>
                  </div>
                </div>

                <div className="mt-5 grid gap-3 md:grid-cols-3">
                  <MetricCard label="ROI" value={formatPercent(memory.latest.roi)} />
                  <MetricCard label="Projected profit" value={formatCurrency(memory.latest.projected_profit)} />
                  <MetricCard label="Confidence" value={formatPercent(memory.latest.confidence)} />
                </div>

                <div className="mt-5 rounded-2xl border border-slate-800 bg-slate-950/50 px-4 py-3 text-sm text-slate-300">
                  <span className="text-slate-500">Change across runs:</span>{" "}
                  {memory.changes.summary ?? "No change summary available."}
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {memory.statusHistory.map((status, index) => (
                    <PipelineStatusPill key={`${memory.parcel_id}-${index}-${status}`} status={status} compact />
                  ))}
                </div>

                <div className="mt-5 flex flex-wrap gap-3">
                  <Link
                    href={`/report/${memory.parcel_id}`}
                    className="inline-flex rounded-2xl border border-cyan-400/40 px-4 py-2 text-sm font-semibold text-cyan-300"
                  >
                    Decision report
                  </Link>
                  <Link
                    href={`/runs/${memory.latest.run_id}`}
                    className="inline-flex rounded-2xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
                  >
                    Open latest saved run
                  </Link>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState copy="No saved parcel memory exists yet. Run the pipeline on at least one parcel to populate this view." />
        )}
      </div>
    </div>
  );
}

function EmptyState({ copy }: { copy: string }) {
  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-8 text-sm text-slate-400">
      {copy}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-2 text-lg font-semibold text-slate-100">{value}</div>
    </div>
  );
}

function StatusPill({
  status,
  compact = false,
}: {
  status: "STRONG" | "MARGINAL" | "PASS" | "NEAR_FEASIBLE";
  compact?: boolean;
}) {
  const tones: Record<string, string> = {
    STRONG: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
    MARGINAL: "border-amber-400/40 bg-amber-400/10 text-amber-300",
    PASS: "border-rose-400/40 bg-rose-400/10 text-rose-300",
    NEAR_FEASIBLE: "border-violet-400/40 bg-violet-400/10 text-violet-300",
  };
  const tone = tones[status] ?? tones.PASS;
  const label = status === "NEAR_FEASIBLE" ? "Near feasible" : status;
  return (
    <span className={`inline-flex rounded-full border ${compact ? "px-2 py-1" : "px-3 py-1"} text-[11px] font-semibold uppercase tracking-[0.18em] ${tone}`}>
      {label}
    </span>
  );
}

function PipelineStatusPill({
  status,
  compact = false,
}: {
  status: "loading" | "completed" | "near_feasible" | "failed";
  compact?: boolean;
}) {
  const tone =
    status === "completed"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
      : status === "near_feasible"
        ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
        : status === "failed"
          ? "border-rose-400/40 bg-rose-400/10 text-rose-300"
          : "border-slate-600 bg-slate-800 text-slate-300";
  return (
    <span className={`inline-flex rounded-full border ${compact ? "px-2 py-1" : "px-3 py-1"} text-[11px] font-semibold uppercase tracking-[0.18em] ${tone}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatCurrency(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}
