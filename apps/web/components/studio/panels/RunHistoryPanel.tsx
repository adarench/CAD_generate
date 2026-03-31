"use client";

import Link from "next/link";

import type { PipelineRun } from "@/lib/parcels";
import { buildParcelMemory } from "@/lib/runMemory";

import { WorkspaceSection } from "./shared";

export function RunHistoryPanel({
  runs,
  formatTimestamp,
}: {
  runs: PipelineRun[];
  formatTimestamp: (value: string) => string;
}) {
  const memory = buildParcelMemory(runs);

  return (
    <WorkspaceSection eyebrow="Saved runs" title="Parcel memory">
      {memory ? (
        <div className="space-y-4">
          <div className="rounded-[20px] border border-slate-800 bg-slate-900/80 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Latest recommendation</p>
                <p className="mt-2 text-base font-semibold text-slate-100">
                  {memory.latest.status}
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-300">Latest saved feasibility result for this parcel.</p>
              </div>
              <StatusPill status={memory.latest.status} />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-slate-400">
              <div>
                <div className="uppercase tracking-[0.18em] text-slate-500">Last updated</div>
                <div className="mt-1 text-slate-200">{formatTimestamp(memory.lastUpdatedAt)}</div>
              </div>
              <div>
                <div className="uppercase tracking-[0.18em] text-slate-500">Saved runs</div>
                <div className="mt-1 text-slate-200">{memory.runCount}</div>
              </div>
            </div>
          </div>

          <div className="rounded-[20px] border border-slate-800 bg-slate-900/60 p-4">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Decision continuity</p>
            <div className="mt-3 space-y-3 text-sm text-slate-300">
              <div>
                <span className="text-slate-500">Current:</span>{" "}
                <span className="font-semibold text-slate-100">{memory.latest.status}</span>
              </div>
              <div>
                <span className="text-slate-500">Previous:</span>{" "}
                <span className="font-semibold text-slate-100">
                  {memory.previous?.status ?? "No prior saved result"}
                </span>
              </div>
              <p className="leading-6 text-slate-400">{memory.changes.summary ?? "No change summary available."}</p>
            </div>
          </div>

          <div className="rounded-[20px] border border-slate-800 bg-slate-900/60 p-4">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Status history</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {memory.statusHistory.map((status, index) => (
                <PipelineStatusPill key={`${status}-${index}`} status={status} compact />
              ))}
            </div>
          </div>

          <div className="space-y-3">
            {memory.runs.map((run) => (
              <HistoryRunCard key={run.run_id} run={run} formatTimestamp={formatTimestamp} />
            ))}
          </div>
        </div>
      ) : (
        <p className="text-sm leading-7 text-slate-400">
          No Bedrock runs saved for this parcel yet. Run the pipeline once to create parcel memory.
        </p>
      )}
    </WorkspaceSection>
  );
}

function HistoryRunCard({
  run,
  formatTimestamp,
}: {
  run: PipelineRun;
  formatTimestamp: (value: string) => string;
}) {
  const roi = run.feasibility_result?.ROI_base ?? run.feasibility_result?.ROI ?? null;
  const profit = run.feasibility_result?.projected_profit ?? null;
  const units = run.layout_result?.unit_count ?? run.feasibility_result?.units ?? null;

  return (
    <Link
      href={`/runs/${run.run_id}`}
      className="block rounded-[20px] border border-slate-800 bg-slate-900/80 px-4 py-4 text-sm text-slate-300 transition hover:border-slate-600"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-slate-100">{run.run_id.slice(0, 8)}</span>
        <PipelineStatusPill status={run.status} />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3 text-xs text-slate-500">
        <Metric label="Updated" value={formatTimestamp(run.timestamp)} />
        <Metric label="Units" value={typeof units === "number" ? String(units) : "—"} />
        <Metric label="ROI" value={formatPercent(roi)} />
      </div>
      <div className="mt-3 text-xs text-slate-400">
        <span className="text-slate-500">Profit:</span> {formatCurrency(profit)}
      </div>
    </Link>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="uppercase tracking-[0.18em]">{label}</div>
      <div className="mt-1 text-slate-200">{value}</div>
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
    <span
      className={`inline-flex rounded-full border ${compact ? "px-2 py-1" : "px-3 py-1"} text-[11px] font-semibold uppercase tracking-[0.18em] ${tone}`}
    >
      {label}
    </span>
  );
}

function PipelineStatusPill({
  status,
  compact = false,
}: {
  status: PipelineRun["status"] | "loading";
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
  const label =
    status === "completed" ? "Completed" : status === "near_feasible" ? "Near feasible" : status === "failed" ? "Failed" : "Loading";
  return (
    <span
      className={`inline-flex rounded-full border ${compact ? "px-2 py-1" : "px-3 py-1"} text-[11px] font-semibold uppercase tracking-[0.18em] ${tone}`}
    >
      {label}
    </span>
  );
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
