import type { PipelineRun } from "@/lib/parcels";

export const STRONG_ROI_THRESHOLD = 0.15;
export const MARGINAL_ROI_TOLERANCE = 0.03;

export type DealStatus = "STRONG" | "MARGINAL" | "PASS" | "NEAR_FEASIBLE";

export type SourceMode = "verified" | "inferred";

export type DealRecord = {
  run_id: string;
  parcel_id: string;
  jurisdiction: string;
  units: number;
  roi: number;
  projected_profit: number;
  confidence: number | null;
  status: DealStatus;
  source_mode: SourceMode;
  pipeline_status: PipelineRun["status"];
  layout_id: string | null;
  scenario_id: string | null;
  key_risk_factors: string[];
  last_run_at: string;
};

export function dealRecordFromPipelineRun(run: PipelineRun): DealRecord | null {
  const feasibility = run.feasibility_result;
  const inferred = run.inferred_analysis;
  const upside = run.near_feasible_result?.financial_upside as Record<string, unknown> | undefined;

  // Preference order: real feasibility → inferred analysis → near_feasible upside
  const roi = feasibility?.ROI_base ?? feasibility?.ROI ?? inferred?.roi ?? asNullableNumber(upside?.ROI);
  const projectedProfit = feasibility?.projected_profit ?? inferred?.projected_profit ?? asNullableNumber(upside?.projected_profit);
  const units = feasibility?.units ?? inferred?.estimated_units_mid ?? asNullableInteger(upside?.relaxed_units) ?? run.layout_result?.unit_count ?? 0;
  const confidence = feasibility?.confidence_score ?? feasibility?.confidence ?? inferred?.confidence ?? null;
  const sourceMode: SourceMode = feasibility && feasibility.units > 0 ? "verified" : inferred ? "inferred" : "verified";

  if (run.status === "near_feasible") {
    const effectiveRoi = typeof roi === "number" && !Number.isNaN(roi) ? roi : 0;
    const effectiveProfit = typeof projectedProfit === "number" && !Number.isNaN(projectedProfit) ? projectedProfit : 0;
    return {
      run_id: run.run_id,
      parcel_id: run.parcel_id,
      jurisdiction: run.zoning_result.jurisdiction ?? inferred?.jurisdiction ?? "Unknown",
      units,
      roi: effectiveRoi,
      projected_profit: effectiveProfit,
      confidence,
      // When inferred_analysis has healthy financials, classify normally rather than always showing NEAR_FEASIBLE
      status: inferred && effectiveRoi !== 0 ? classifyDealStatus(effectiveRoi, effectiveProfit) : "NEAR_FEASIBLE",
      source_mode: sourceMode,
      pipeline_status: run.status,
      layout_id: run.layout_result?.layout_id ?? feasibility?.layout_id ?? null,
      scenario_id: feasibility?.scenario_id ?? null,
      key_risk_factors: feasibility?.key_risk_factors ?? [],
      last_run_at: run.timestamp,
    };
  }

  if (typeof roi !== "number" || Number.isNaN(roi)) return null;
  if (typeof projectedProfit !== "number" || Number.isNaN(projectedProfit)) return null;

  return {
    run_id: run.run_id,
    parcel_id: run.parcel_id,
    jurisdiction: run.zoning_result.jurisdiction ?? "Unknown",
    units,
    roi,
    projected_profit: projectedProfit,
    confidence,
    status: classifyDealStatus(roi, projectedProfit),
    source_mode: sourceMode,
    pipeline_status: run.status,
    layout_id: run.layout_result?.layout_id ?? feasibility?.layout_id ?? null,
    scenario_id: feasibility?.scenario_id ?? null,
    key_risk_factors: feasibility?.key_risk_factors ?? [],
    last_run_at: run.timestamp,
  };
}

export function classifyDealStatus(roi: number, projectedProfit: number): DealStatus {
  if (projectedProfit < 0 || roi < -MARGINAL_ROI_TOLERANCE) {
    return "PASS";
  }
  if (roi > STRONG_ROI_THRESHOLD) {
    return "STRONG";
  }
  return "MARGINAL";
}

function asNullableNumber(value: unknown) {
  return typeof value === "number" && !Number.isNaN(value) ? value : null;
}

function asNullableInteger(value: unknown) {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}
