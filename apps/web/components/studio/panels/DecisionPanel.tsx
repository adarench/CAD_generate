"use client";

import { decisionRecordFromPipelineRun } from "@/lib/opportunities";
import type { PipelineRun } from "@/lib/parcels";

import { MetricCard, WorkspaceSection } from "./shared";

export function DecisionPanel({ resolvedRun }: { resolvedRun: PipelineRun | null }) {
  if (!resolvedRun) {
    return (
      <WorkspaceSection eyebrow="Decision" title="What should I do with this land?">
        <p className="text-sm leading-7 text-slate-400">
          Run the pipeline to generate a decision label, summary, and confidence score for this parcel.
        </p>
      </WorkspaceSection>
    );
  }

  const decision = decisionRecordFromPipelineRun(resolvedRun);

  return (
    <WorkspaceSection eyebrow="Decision" title="What should I do with this land?">
      <div className="flex flex-wrap items-center gap-3">
        <DecisionBadge label={decision.decision_label} />
        <StatusBadge status={resolvedRun.status} />
      </div>
      <p className="mt-4 text-sm leading-7 text-slate-300">{decision.decision_summary}</p>
      <div className="mt-4 grid gap-3">
        <MetricCard label="Confidence score" value={formatPercent(decision.confidence_score)} />
      </div>
    </WorkspaceSection>
  );
}

function DecisionBadge({ label }: { label: "BUY" | "CONDITIONAL" | "PASS" | "PENDING" }) {
  const tone =
    label === "BUY"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
      : label === "CONDITIONAL"
        ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
        : label === "PENDING"
          ? "border-slate-500/40 bg-slate-500/10 text-slate-300"
          : "border-rose-400/40 bg-rose-400/10 text-rose-300";

  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] ${tone}`}>
      {label}
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
