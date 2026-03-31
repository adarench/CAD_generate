"use client";

import { dealRecordFromPipelineRun } from "@/lib/opportunities";
import type { PipelineRun } from "@/lib/parcels";

import { MetricCard, WorkspaceSection } from "./shared";

export function DecisionPanel({ resolvedRun }: { resolvedRun: PipelineRun | null }) {
  if (!resolvedRun) {
    return (
      <WorkspaceSection eyebrow="Decision" title="What should I do with this land?">
        <p className="text-sm leading-7 text-slate-400">
          Run the pipeline to generate a feasibility-backed deal status and confidence score for this parcel.
        </p>
      </WorkspaceSection>
    );
  }

  const deal = dealRecordFromPipelineRun(resolvedRun);
  if (!deal) {
    return (
      <WorkspaceSection eyebrow="Decision" title="What should I do with this land?">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={resolvedRun.status} />
        </div>
        <p className="mt-4 text-sm leading-7 text-slate-300">
          This parcel has not produced a persisted feasibility result yet, so it is not part of the
          Opportunities decision surface.
        </p>
      </WorkspaceSection>
    );
  }

  return (
    <WorkspaceSection eyebrow="Decision" title="What should I do with this land?">
      <div className="flex flex-wrap items-center gap-3">
        <DealBadge label={deal.status} />
        <StatusBadge status={resolvedRun.status} />
      </div>
      <p className="mt-4 text-sm leading-7 text-slate-300">
        Studio is the inspection surface. The current deal status is derived from the saved feasibility result.
      </p>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <MetricCard label="Deal status" value={deal.status} />
        <MetricCard label="Confidence" value={formatPercent(deal.confidence)} />
        <MetricCard label="ROI" value={formatPercent(deal.roi)} />
      </div>
    </WorkspaceSection>
  );
}

function DealBadge({ label }: { label: "STRONG" | "MARGINAL" | "PASS" | "NEAR_FEASIBLE" }) {
  const tones: Record<string, string> = {
    STRONG: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
    MARGINAL: "border-amber-400/40 bg-amber-400/10 text-amber-300",
    PASS: "border-rose-400/40 bg-rose-400/10 text-rose-300",
    NEAR_FEASIBLE: "border-violet-400/40 bg-violet-400/10 text-violet-300",
  };
  const tone = tones[label] ?? tones.PASS;
  const display = label === "NEAR_FEASIBLE" ? "Near feasible" : label;

  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] ${tone}`}>
      {display}
    </span>
  );
}

function StatusBadge({ status }: { status: PipelineRun["status"] }) {
  const tone =
    status === "completed"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
      : status === "near_feasible"
        ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
        : "border-rose-400/40 bg-rose-400/10 text-rose-300";

  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] ${tone}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function formatPercent(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}
