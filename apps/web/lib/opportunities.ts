import type { PipelineRun } from "@/lib/parcels";

export const STRONG_ROI_THRESHOLD = 0.15;
export const MARGINAL_ROI_TOLERANCE = 0.03;

export type DealStatus = "STRONG" | "MARGINAL" | "PASS" | "NEAR_FEASIBLE";

export type DealRecord = {
  run_id: string;
  parcel_id: string;
  jurisdiction: string;
  units: number;
  roi: number;
  projected_profit: number;
  confidence: number | null;
  status: DealStatus;
  pipeline_status: PipelineRun["status"];
  layout_id: string | null;
  scenario_id: string | null;
  key_risk_factors: string[];
  last_run_at: string;
};

export function dealRecordFromPipelineRun(run: PipelineRun): DealRecord | null {
  const feasibility = run.feasibility_result;
  const upside = run.near_feasible_result?.financial_upside as Record<string, unknown> | undefined;

  const roi = feasibility?.ROI_base ?? feasibility?.ROI ?? asNullableNumber(upside?.ROI);
  const projectedProfit = feasibility?.projected_profit ?? asNullableNumber(upside?.projected_profit);
  const units = feasibility?.units ?? asNullableInteger(upside?.relaxed_units) ?? run.layout_result?.unit_count ?? 0;

  if (run.status === "near_feasible") {
    return {
      run_id: run.run_id,
      parcel_id: run.parcel_id,
      jurisdiction: run.zoning_result.jurisdiction ?? "Unknown",
      units,
      roi: typeof roi === "number" && !Number.isNaN(roi) ? roi : 0,
      projected_profit: typeof projectedProfit === "number" && !Number.isNaN(projectedProfit) ? projectedProfit : 0,
      confidence: feasibility?.confidence_score ?? feasibility?.confidence ?? null,
      status: "NEAR_FEASIBLE",
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
    confidence: feasibility?.confidence_score ?? feasibility?.confidence ?? null,
    status: classifyDealStatus(roi, projectedProfit),
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
