import type { DiscoveryParcelRecord, PipelineRun } from "@/lib/parcels";

export type DecisionLabel = "BUY" | "CONDITIONAL" | "PASS" | "PENDING";

export type DecisionRecord = {
  run_id: string;
  parcel_id: string;
  jurisdiction: string;
  status: "completed" | "near_feasible" | "failed" | "loading";
  decision_label: DecisionLabel;
  decision_summary: string;
  units: number | null;
  ROI_base: number | null;
  ROI_best_case: number | null;
  ROI_worst_case: number | null;
  projected_profit: number | null;
  confidence_score: number | null;
  key_risk_factors: string[];
  near_feasible_flag: boolean;
  near_feasible_summary: string | null;
  blocker_summary: string | null;
  upside_summary: string | null;
  provenance_summary: string;
  last_run_at: string;
  has_run: boolean;
};

export function decisionRecordFromPipelineRun(run: PipelineRun): DecisionRecord {
  const roiBase = run.feasibility_result?.ROI_base ?? run.feasibility_result?.ROI ?? null;
  const confidenceScore =
    run.feasibility_result?.confidence_score ?? run.feasibility_result?.confidence ?? null;
  const nearFeasibleFlag = Boolean(run.near_feasible_result) || run.status === "near_feasible";
  const nearFeasibleSummary = summarizeNearFeasible(run);
  const blockerSummary = summarizeBlockers(run);
  const upsideSummary = summarizeUpside(run);

  return {
    run_id: run.run_id,
    parcel_id: run.parcel_id,
    jurisdiction: run.zoning_result.jurisdiction ?? "Unknown",
    status: run.status,
    decision_label: deriveDecisionLabel(run.status, roiBase, confidenceScore),
    decision_summary: buildDecisionSummary(run.status, roiBase, confidenceScore, nearFeasibleSummary),
    units: run.layout_result?.unit_count ?? run.feasibility_result?.units ?? null,
    ROI_base: roiBase,
    ROI_best_case: run.feasibility_result?.ROI_best_case ?? null,
    ROI_worst_case: run.feasibility_result?.ROI_worst_case ?? null,
    projected_profit: run.feasibility_result?.projected_profit ?? null,
    confidence_score: confidenceScore,
    key_risk_factors: run.feasibility_result?.key_risk_factors ?? [],
    near_feasible_flag: nearFeasibleFlag,
    near_feasible_summary: nearFeasibleSummary,
    blocker_summary: blockerSummary,
    upside_summary: upsideSummary,
    provenance_summary: buildProvenanceSummary(run),
    last_run_at: run.timestamp,
    has_run: true,
  };
}

export function placeholderDecisionRecord(
  parcelId: string,
  parcel: DiscoveryParcelRecord | undefined,
  pipelineError: unknown
): DecisionRecord {
  const errorMessage = pipelineError instanceof Error ? pipelineError.message : null;
  return {
    run_id: `pending:${parcelId}`,
    parcel_id: parcelId,
    jurisdiction: parcel?.county ? `${parcel.county} County` : "Loading parcel",
    status: errorMessage ? "failed" : "loading",
    decision_label: errorMessage ? "PASS" : "PENDING",
    decision_summary: errorMessage
      ? "Pipeline evaluation failed before a decision record could be completed."
      : "Parcel is shortlisted and awaiting full pipeline evaluation.",
    units: null,
    ROI_base: null,
    ROI_best_case: null,
    ROI_worst_case: null,
    projected_profit: null,
    confidence_score: null,
    key_risk_factors: errorMessage ? [errorMessage] : [],
    near_feasible_flag: false,
    near_feasible_summary: null,
    blocker_summary: errorMessage ?? null,
    upside_summary: null,
    provenance_summary: errorMessage
      ? "Derived from shortlist parcel record with pipeline error."
      : "Derived from shortlist parcel record before a saved run exists.",
    last_run_at: parcel?.fetchedAt ?? new Date(0).toISOString(),
    has_run: false,
  };
}

function deriveDecisionLabel(
  status: DecisionRecord["status"],
  roiBase: number | null,
  confidenceScore: number | null
): DecisionLabel {
  if (status === "loading") return "PENDING";
  if (status === "near_feasible") return "CONDITIONAL";
  if (status === "failed") return "PASS";
  if (typeof roiBase === "number" && roiBase > 0 && typeof confidenceScore === "number" && confidenceScore >= 0.6) {
    return "BUY";
  }
  if (typeof roiBase === "number" && roiBase > 0) {
    return "CONDITIONAL";
  }
  return "PASS";
}

function buildDecisionSummary(
  status: DecisionRecord["status"],
  roiBase: number | null,
  confidenceScore: number | null,
  nearFeasibleSummary: string | null
) {
  if (status === "loading") {
    return "Shortlisted parcel is being evaluated through the live pipeline.";
  }
  if (status === "near_feasible") {
    return nearFeasibleSummary
      ? `Near feasible — ${nearFeasibleSummary}`
      : "Near feasible — explicit constraint relief is required.";
  }
  if (status === "failed") {
    return "Pass — pipeline did not produce a decision-grade result.";
  }
  if (typeof roiBase === "number" && roiBase > 0) {
    if (typeof confidenceScore === "number" && confidenceScore >= 0.6) {
      return "Completed with positive ROI and high confidence.";
    }
    return "Completed with positive ROI, but confidence remains limited.";
  }
  return "Pass — negative economics under current assumptions.";
}

function summarizeNearFeasible(run: PipelineRun): string | null {
  if (!run.near_feasible_result) return null;
  const blockers = Object.keys(run.near_feasible_result.required_relaxation ?? {});
  const blockerSummary = blockers.length ? blockers.slice(0, 2).join(", ") : null;
  const reason = blockerSummary
    ? `${blockerSummary.replace(/_/g, " ")} relaxation required`
    : run.near_feasible_result.reason_category.replace(/_/g, " ");
  return reason;
}

function summarizeBlockers(run: PipelineRun): string | null {
  if (run.near_feasible_result) {
    const blockers = Object.keys(run.near_feasible_result.limiting_constraints ?? {});
    if (blockers.length) {
      return blockers
        .slice(0, 2)
        .map((value) => value.replace(/_/g, " "))
        .join(", ");
    }
    return run.near_feasible_result.reason_category.replace(/_/g, " ");
  }
  if (run.feasibility_result?.key_risk_factors?.length) {
    return run.feasibility_result.key_risk_factors.slice(0, 2).join(", ");
  }
  if (run.status === "failed") {
    return "Pipeline failed to produce a decision-grade output";
  }
  return null;
}

function summarizeUpside(run: PipelineRun): string | null {
  const upside = run.near_feasible_result?.financial_upside;
  if (!upside || typeof upside !== "object") return null;
  const record = upside as Record<string, unknown>;
  if (typeof record.delta_roi === "number") {
    return `ROI upside ${formatPercent(record.delta_roi)}`;
  }
  if (typeof record.delta_profit === "number") {
    return `Profit upside ${formatCurrency(record.delta_profit)}`;
  }
  if (typeof record.estimated_profit_if_resolved === "number") {
    return `Resolved profit ${formatCurrency(record.estimated_profit_if_resolved)}`;
  }
  const keys = Object.keys(record);
  if (keys.length) {
    return keys
      .slice(0, 2)
      .map((value) => value.replace(/_/g, " "))
      .join(", ");
  }
  return null;
}

function buildProvenanceSummary(run: PipelineRun) {
  const inputs: string[] = [];
  if (run.zoning_result.district) {
    inputs.push(`district ${run.zoning_result.district}`);
  }
  if (run.layout_result?.layout_id) {
    inputs.push(`layout ${run.layout_result.layout_id}`);
  }
  if (run.feasibility_result?.scenario_id) {
    inputs.push(`scenario ${run.feasibility_result.scenario_id}`);
  }
  if (run.zoning_bypassed) {
    inputs.push(`zoning bypassed${run.bypass_reason ? ` (${run.bypass_reason})` : ""}`);
  }
  return inputs.length ? `Derived from ${inputs.join(" • ")}.` : "Derived from current pipeline run.";
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}
