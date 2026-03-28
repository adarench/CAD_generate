"use client";

import type { PipelineRun } from "@/lib/parcels";

import { MetricCard, WorkspaceSection } from "./shared";

export function FeasibilityPanel({ resolvedRun }: { resolvedRun: PipelineRun | null }) {
  return (
    <WorkspaceSection eyebrow="Economics" title="Expected economic outcome">
      {resolvedRun?.feasibility_result ? (
        <div className="space-y-3">
          <MetricCard label="Projected profit" value={formatCurrency(resolvedRun.feasibility_result.projected_profit)} />
          <MetricCard label="ROI base" value={formatPercent(resolvedRun.feasibility_result.ROI_base ?? resolvedRun.feasibility_result.ROI)} />
          <MetricCard label="ROI best case" value={formatPercent(resolvedRun.feasibility_result.ROI_best_case)} />
          <MetricCard label="ROI worst case" value={formatPercent(resolvedRun.feasibility_result.ROI_worst_case)} />
          <MetricCard label="Break-even price" value={formatCurrency(resolvedRun.feasibility_result.break_even_price)} />
          <MetricCard label="Revenue" value={formatCurrency(resolvedRun.feasibility_result.projected_revenue)} />
          <MetricCard label="Cost" value={formatCurrency(resolvedRun.feasibility_result.projected_cost)} />
          <MetricCard
            label="Confidence"
            value={formatPercent(resolvedRun.feasibility_result.confidence_score ?? resolvedRun.feasibility_result.confidence)}
          />
        </div>
      ) : resolvedRun ? (
        <p className="text-sm leading-7 text-slate-400">
          Economic outputs are only available when the pipeline reaches the feasibility stage.
        </p>
      ) : (
        <p className="text-sm leading-7 text-slate-400">
          Run the pipeline to generate economics for this parcel.
        </p>
      )}
    </WorkspaceSection>
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
