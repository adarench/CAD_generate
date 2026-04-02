"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery, useQueries, useQueryClient } from "@tanstack/react-query";

import { createDecision, ensureBedrockParcel, fetchDecisions, fetchOptimizationRuns, fetchOptimizationRun, fetchRun, fetchRuns } from "@/lib/api";
import { ScenarioTable, type ScenarioRow } from "@/components/report/ScenarioTable";
import { ConstraintExplainer } from "@/components/report/ConstraintExplainer";
import { WhatIfCalculator } from "@/components/report/WhatIfCalculator";
import { DealSolver } from "@/components/report/DealSolver";
import {
  dealRecordFromPipelineRun,
  classifyDealStatus,
  type DealRecord,
  type DealStatus,
} from "@/lib/opportunities";
import type {
  BedrockFeasibilityResult,
  BedrockParcel,
  CandidateSensitivity,
  EconomicScenario,
  NearFeasibleResult,
  OptimizationDecision,
  OptimizationRun,
  PipelineRun,
  SensitivityBreakpoint,
} from "@/lib/parcels";

interface DecisionReportProps {
  parcelId: string;
}

export function DecisionReport({ parcelId }: DecisionReportProps) {
  const parcelQuery = useQuery({
    queryKey: ["report-parcel", parcelId],
    queryFn: () => ensureBedrockParcel(parcelId),
    retry: false,
  });

  const runsIndexQuery = useQuery({
    queryKey: ["report-runs-index"],
    queryFn: () => fetchRuns({ limit: 120, sort: "timestamp", order: "desc" }),
  });

  const parcelRunSummaries = useMemo(
    () => (runsIndexQuery.data ?? []).filter((run) => run.parcel_id === parcelId).slice(0, 8),
    [parcelId, runsIndexQuery.data]
  );

  const runDetailQueries = useQueries({
    queries: parcelRunSummaries.map((summary) => ({
      queryKey: ["report-run", summary.run_id],
      queryFn: () => fetchRun(summary.run_id),
      retry: false,
      staleTime: 30_000,
    })),
  });

  const parcelRuns = useMemo(
    () =>
      runDetailQueries
        .map((q) => q.data)
        .filter((run): run is PipelineRun => Boolean(run))
        .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp)),
    [runDetailQueries]
  );

  const optimizationIndexQuery = useQuery({
    queryKey: ["report-optimization-runs", parcelId],
    queryFn: () => fetchOptimizationRuns({ limit: 20 }),
  });

  const parcelOptRunSummaries = useMemo(
    () => (optimizationIndexQuery.data ?? []).filter((r) => r.parcel_id === parcelId).slice(0, 3),
    [parcelId, optimizationIndexQuery.data]
  );

  const latestOptSummary = parcelOptRunSummaries[0] ?? null;
  const optimizationRunQuery = useQuery({
    queryKey: ["report-optimization-run", latestOptSummary?.optimization_run_id],
    queryFn: () => fetchOptimizationRun(latestOptSummary!.optimization_run_id),
    enabled: Boolean(latestOptSummary?.optimization_run_id),
    retry: false,
    staleTime: 30_000,
  });

  const latestRun = parcelRuns[0] ?? null;
  const deal = latestRun ? dealRecordFromPipelineRun(latestRun) : null;
  const parcel = parcelQuery.data ?? null;
  const feasibility = latestRun?.feasibility_result ?? null;
  const nearFeasible = latestRun?.near_feasible_result ?? null;
  const optimizationRun = optimizationRunQuery.data ?? null;
  const optDecision = optimizationRun?.decision ?? null;

  const decisionsQuery = useQuery({
    queryKey: ["report-decisions", parcelId],
    queryFn: () => fetchDecisions({ parcel_id: parcelId, limit: 5 }),
  });
  const existingDecision = (decisionsQuery.data ?? [])[0] ?? null;

  // Inferred analysis is auto-attached to the run by the pipeline when zoning is bypassed or layout fails.
  const inferredResult = latestRun?.inferred_analysis ?? null;
  const [userScenarios, setUserScenarios] = useState<ScenarioRow[]>([]);

  const isNearFeasibleWithNoFinancials = latestRun?.status === "near_feasible" && !latestRun?.feasibility_result;
  const shouldOfferInference = (!latestRun || isNearFeasibleWithNoFinancials) && !inferredResult;

  const isLoading =
    parcelQuery.isLoading ||
    runsIndexQuery.isLoading ||
    runDetailQueries.some((q) => q.isLoading);

  if (isLoading) {
    return (
      <div className="px-6 py-10">
        <div className="mx-auto max-w-[1100px]">
          <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-10 text-sm text-slate-400">
            Loading decision report for {parcelId}...
          </div>
        </div>
      </div>
    );
  }

  if (shouldOfferInference) {
    return (
      <div className="px-6 py-10">
        <div className="mx-auto max-w-[1100px]">
          <ReportHeader parcelId={parcelId} parcel={parcel} />
          <div className="mt-8 rounded-[28px] border border-dashed border-slate-700 bg-slate-900/70 p-10">
            <div className="text-xs uppercase tracking-[0.28em] text-slate-500">No evaluation data</div>
            <h2 className="mt-3 text-2xl font-semibold text-slate-100">
              This parcel has not been evaluated yet.
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
              Run feasibility or deep evaluate from Discovery to generate analysis.
              For parcels without overlay zoning, the system will automatically produce an AI-inferred estimate.
            </p>
            <div className="mt-6 flex gap-3">
              <Link href="/map" className="rounded-2xl bg-cyan-400 px-5 py-3 text-sm font-semibold uppercase tracking-[0.22em] text-slate-950">
                Open Discovery
              </Link>
              <Link href="/opportunities" className="rounded-2xl border border-slate-700 px-5 py-3 text-sm font-semibold text-slate-200">
                Back to Opportunities
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Unified render — both DECISION and INFERRED parcels use the same layout.
  // The inferred banner appears at the top when applicable.
  return (
    <div className="px-6 py-10">
      <div className="mx-auto max-w-[1100px]">
        <ReportHeader parcelId={parcelId} parcel={parcel} />
        <CoverageIndicator run={latestRun} inferredResult={inferredResult} />

        {inferredResult && !feasibility ? (
          <div className="mt-6 rounded-[28px] border border-violet-400/40 bg-violet-400/8 p-6">
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-violet-300">
                Inferred analysis
              </div>
              <span className="rounded-full border border-violet-400/40 bg-violet-400/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-violet-300">
                AI-estimated · not overlay-backed
              </span>
            </div>
            <h2 className="mt-3 text-xl font-semibold text-violet-100">
              {inferredResult.recommendation.replace(/_/g, " ")}
            </h2>
            <p className="mt-2 text-sm leading-7 text-violet-200/80">
              {inferredResult.reasoning_summary}
            </p>
            <div className="mt-3 text-xs text-amber-300">
              All metrics below are estimated. Verify with local planning before committing.
            </div>
          </div>
        ) : null}

        <div className="mt-8 grid gap-6">
          <DealMemo
            deal={deal}
            feasibility={feasibility}
            run={latestRun}
            parcel={parcel}
            optDecision={optDecision}
          />
          <RecommendationBanner deal={deal} run={latestRun} nearFeasible={nearFeasible} optDecision={optDecision} />
          <ScenarioTable
            feasibility={feasibility}
            optDecision={optDecision}
            optimizationRun={optimizationRun}
            inferredAnalysis={inferredResult}
            userScenarios={userScenarios}
          />
          <ConstraintExplainer
            feasibility={feasibility}
            zoningResult={latestRun.zoning_result}
            areaAcres={parcel ? parcel.area_sqft / 43560 : 0}
            optDecision={optDecision}
            economicScenarios={optimizationRun?.economic_scenarios ?? []}
          />
          <SummaryMetrics deal={deal} feasibility={feasibility} run={latestRun} optDecision={optDecision} />
          <WhatIfCalculator
            parcelId={parcelId}
            feasibility={feasibility}
            inferredAnalysis={inferredResult}
            onScenarioCreated={(scenario) => setUserScenarios((prev) => [...prev, scenario])}
          />
          <DealSolver
            feasibility={feasibility}
            layoutResult={latestRun?.layout_result ?? null}
            parcelAreaSqft={parcel?.area_sqft ?? null}
          />
          <ConfidenceBreakdown feasibility={feasibility} />
          <AssumptionCard feasibility={feasibility} run={latestRun} />
          <SensitivitySection feasibility={feasibility} optDecision={optDecision} />
          {optDecision?.breakpoints?.length ? <BreakpointSection breakpoints={optDecision.breakpoints} /> : null}
          {optimizationRun?.economic_scenarios?.length ? <EconomicScenariosSection scenarios={optimizationRun.economic_scenarios} /> : null}
          {optimizationRun?.sensitivity_analysis?.length ? <CandidateSensitivitySection analysis={optimizationRun.sensitivity_analysis} /> : null}
          {nearFeasible ? <NearFeasibleSection nearFeasible={nearFeasible} run={latestRun} /> : null}
          <NextActions deal={deal} run={latestRun} parcelId={parcelId} nearFeasible={nearFeasible} optDecision={optDecision} />
          <RecordDecisionPanel
            parcelId={parcelId}
            optimizationRunId={optimizationRun?.optimization_run_id ?? null}
            pipelineRunId={latestRun.run_id}
            systemRecommendation={optDecision?.recommendation ?? null}
            targetPrice={optDecision?.target_price ?? null}
            existingDecision={existingDecision}
          />
          <RoutingDebugPanel run={latestRun} inferredResult={inferredResult} />
          <NavigationFooter parcelId={parcelId} run={latestRun} />
        </div>
      </div>
    </div>
  );
}

function CoverageIndicator({ run, inferredResult }: { run: PipelineRun | null; inferredResult: import("@/lib/parcels").InferredAnalysis | null }) {
  if (!run) return null;

  const bypassed = run.zoning_bypassed;
  const hasInferred = Boolean(inferredResult || run.inferred_analysis);
  const hasFeasibility = Boolean(run.feasibility_result?.units);

  if (hasFeasibility && !bypassed) {
    return (
      <div className="mt-4 flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/5 px-4 py-2">
        <span className="h-2 w-2 rounded-full bg-emerald-400" />
        <span className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300">Verified</span>
        <span className="text-xs text-emerald-200/60">Zoning resolved from authoritative GIS data</span>
      </div>
    );
  }

  if (hasInferred) {
    return (
      <div className="mt-4 flex items-center gap-2 rounded-full border border-violet-400/30 bg-violet-400/5 px-4 py-2">
        <span className="h-2 w-2 rounded-full bg-violet-400" />
        <span className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-300">Inferred</span>
        <span className="text-xs text-violet-200/60">Zoning estimated — verify before committing</span>
      </div>
    );
  }

  return (
    <div className="mt-4 flex items-center gap-2 rounded-full border border-rose-400/30 bg-rose-400/5 px-4 py-2">
      <span className="h-2 w-2 rounded-full bg-rose-400" />
      <span className="text-xs font-semibold uppercase tracking-[0.2em] text-rose-300">Limited</span>
      <span className="text-xs text-rose-200/60">Insufficient data for reliable evaluation</span>
    </div>
  );
}

function RoutingDebugPanel({ run, inferredResult }: { run: PipelineRun; inferredResult: import("@/lib/parcels").InferredAnalysis | null }) {
  const [open, setOpen] = useState(false);
  const zr = run.zoning_result;
  const md = (zr as unknown as Record<string, unknown>)?.metadata as Record<string, unknown> | undefined;
  const ia = inferredResult ?? (run.inferred_analysis as import("@/lib/parcels").InferredAnalysis | null);

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-6 py-4 text-left"
      >
        <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
          Routing & debug
        </div>
        <span className="text-xs text-slate-500">{open ? "▲" : "▼"}</span>
      </button>
      {open ? (
        <div className="border-t border-slate-800 px-6 pb-6 pt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <DebugField label="Decision path" value={run.zoning_bypassed ? "INFERRED" : "VERIFIED"} />
            <DebugField label="Reason" value={run.zoning_bypassed ? (run.bypass_reason?.replace(/_/g, " ") ?? "Zoning bypass") : "Overlay match found"} />
            <DebugField label="Jurisdiction" value={zr?.jurisdiction ?? "Unknown"} />
            <DebugField label="Zoning district" value={zr?.district ?? "Unknown"} />
            <DebugField label="Source type" value={String(md?.source_type ?? "unknown")} />
            <DebugField label="Legal reliability" value={String(md?.legal_reliability ?? "unknown")} />
            <DebugField label="Rule completeness" value={typeof md?.rule_completeness === "number" ? `${(md.rule_completeness as number * 100).toFixed(0)}%` : "unknown"} />
            <DebugField label="Pipeline status" value={run.status} />
          </div>

          {zr ? (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-600 mb-2">Constraint inputs</div>
              <div className="grid gap-2 sm:grid-cols-3 text-sm">
                <DebugField label="Min lot size" value={zr.min_lot_size_sqft ? `${zr.min_lot_size_sqft.toLocaleString()} sqft` : "—"} />
                <DebugField label="Max density" value={zr.max_units_per_acre ? `${zr.max_units_per_acre} du/ac` : "—"} />
                <DebugField label="Setbacks" value={zr.setbacks ? `F${zr.setbacks.front ?? "?"}/S${zr.setbacks.side ?? "?"}/R${zr.setbacks.rear ?? "?"}` : "—"} />
              </div>
            </div>
          ) : null}

          {ia ? (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-600 mb-2">Inference details</div>
              <div className="grid gap-2 sm:grid-cols-2">
                <DebugField label="Confidence" value={`${Math.round(ia.confidence * 100)}%`} />
                <DebugField label="Zoning assumption" value={ia.zoning_assumption} />
              </div>
              <div className="mt-2 text-xs text-slate-400">{ia.reasoning_summary}</div>
              {ia.key_assumptions?.length ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {ia.key_assumptions.map((a, i) => (
                    <span key={i} className="rounded border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400">{a}</span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="text-[10px] text-slate-600">
            Run ID: {run.run_id} · {run.timestamp}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function DebugField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-600">{label}</div>
      <div className="mt-0.5 text-xs text-slate-300">{value}</div>
    </div>
  );
}

function ReportHeader({ parcelId, parcel }: { parcelId: string; parcel: BedrockParcel | null }) {
  const jurisdiction = parcel?.jurisdiction ?? null;
  const acres = parcel ? (parcel.area_sqft / 43560).toFixed(2) : null;
  const district = parcel?.zoning_district ?? null;

  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="text-xs uppercase tracking-[0.32em] text-slate-500">Decision report</div>
        <h1 className="mt-2 text-3xl font-semibold text-slate-100">{parcelId}</h1>
        <div className="mt-2 flex flex-wrap gap-3 text-sm text-slate-400">
          {jurisdiction ? <span>{jurisdiction}</span> : null}
          {acres ? <span>{acres} ac</span> : null}
          {district ? <span>{district}</span> : null}
        </div>
      </div>
      <div className="flex gap-3">
        <Link
          href="/opportunities"
          className="rounded-2xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
        >
          Back to Opportunities
        </Link>
      </div>
    </div>
  );
}

function DealMemo({
  deal,
  feasibility,
  run,
  parcel,
  optDecision,
}: {
  deal: DealRecord | null;
  feasibility: BedrockFeasibilityResult | null;
  run: PipelineRun;
  parcel: BedrockParcel | null;
  optDecision: OptimizationDecision | null;
}) {
  if (!deal && !feasibility) return null;

  const fs = feasibility?.financial_summary as Record<string, unknown> | undefined;
  const mc = fs?.market_context as Record<string, unknown> | undefined;
  const jurisdiction = parcel?.jurisdiction ?? "Unknown";
  const acres = parcel ? (parcel.area_sqft / 43560).toFixed(1) : "?";
  const district = run.zoning_result?.district ?? "Unknown";
  const units = feasibility?.units ?? deal?.units ?? 0;
  const homePrice = feasibility?.estimated_home_price ?? 0;
  const costPerHome = feasibility?.construction_cost_per_home ?? 0;
  const revenue = feasibility?.projected_revenue ?? 0;
  const cost = feasibility?.projected_cost ?? 0;
  const profit = feasibility?.projected_profit ?? 0;
  const roi = feasibility?.ROI_base ?? feasibility?.ROI ?? deal?.roi;
  const confidence = feasibility?.confidence_score ?? feasibility?.confidence ?? 0;
  const median = (mc?.median_home_value as number) ?? null;
  const usedCountyFallback = Boolean(mc?.used_county_fallback);
  const rec = optDecision?.recommendation?.replace(/_/g, " ") ?? null;

  const roiStr = typeof roi === "number" ? `${(roi * 100).toFixed(1)}%` : "N/A";
  const revenueSource = usedCountyFallback ? "county-level Census fallback" : "jurisdiction-specific Census ACS 2024";
  const calSource = mc?.calibration_source as string | undefined;
  const pricingProxy = mc?.pricing_proxy as string | undefined;
  const evalGrade = (fs?.evaluation_grade as string) ?? null;
  const zoningRules = run.zoning_result;
  const minLot = zoningRules?.min_lot_size_sqft;
  const maxDensity = zoningRules?.max_units_per_acre;
  const acresNum = parcel ? parcel.area_sqft / 43560 : 0;
  const theoreticalMax = maxDensity && acresNum ? Math.floor(acresNum * maxDensity) : null;

  const gradeTone = evalGrade === "DECISION_GRADE"
    ? "border-emerald-400/30 bg-emerald-400/5"
    : evalGrade === "EXPLORATORY"
      ? "border-amber-400/30 bg-amber-400/5"
      : "border-slate-700 bg-slate-900/50";

  const gradeLabel = evalGrade === "DECISION_GRADE"
    ? "Decision-grade — real zoning + calibrated assumptions"
    : evalGrade === "EXPLORATORY"
      ? "Exploratory — estimated data, verify before committing"
      : evalGrade === "BLOCKED"
        ? "Blocked — insufficient data for reliable evaluation"
        : null;

  return (
    <div className={`rounded-[28px] border p-6 ${gradeTone}`}>
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
          Deal memo
        </div>
        {gradeLabel ? (
          <span className={`text-[10px] font-semibold uppercase tracking-[0.18em] ${
            evalGrade === "DECISION_GRADE" ? "text-emerald-300" : evalGrade === "EXPLORATORY" ? "text-amber-300" : "text-slate-500"
          }`}>
            {gradeLabel}
          </span>
        ) : null}
      </div>
      <div className="mt-4 space-y-3 text-sm leading-7 text-slate-300">
        <p>
          <strong className="text-slate-100">{units}-unit subdivision</strong> in {jurisdiction} on {acres} acres
          zoned <strong className="text-slate-100">{district}</strong>.
          {" "}Projected profit of <strong className="text-slate-100">{formatCurrency(profit)}</strong> at{" "}
          <strong className="text-slate-100">{roiStr} ROI</strong> with {Math.round(confidence * 100)}% confidence.
          {rec ? <> System recommendation: <strong className="text-slate-100">{rec}</strong>.</> : null}
        </p>

        {minLot || maxDensity ? (
          <p>
            <strong className="text-slate-200">Key constraints:</strong>{" "}
            {minLot ? `Minimum lot size ${minLot.toLocaleString()} sqft. ` : ""}
            {maxDensity ? `Maximum density ${maxDensity} units/acre. ` : ""}
            {theoreticalMax ? `Theoretical maximum ~${theoreticalMax} units on ${acres} acres. ` : ""}
            {units > 0 && theoreticalMax ? `Layout engine produced ${units} buildable lots after roads, setbacks, and infrastructure.` : ""}
          </p>
        ) : null}

        <p>
          Revenue assumes {units} homes at {formatCurrency(homePrice)} each
          {pricingProxy?.startsWith("internal") ? " (from internal closed-deal data)" : `, based on ${revenueSource} data`}
          {median ? ` (median ${formatCurrency(median)})` : ""}.
          {" "}Construction estimated at {formatCurrency(costPerHome)}/home
          {calSource?.includes("internal") ? " (calibrated from actual builder margins)" : " using regional cost proxy"}.
          {" "}Total cost including land, infrastructure, and soft costs: {formatCurrency(cost)}.
        </p>

        {profit > 0 && typeof roi === "number" ? (
          <p className="text-emerald-200">
            <strong>Why this works:</strong> At {formatCurrency(homePrice)}/home and {formatCurrency(costPerHome)} total cost,
            the margin of {formatCurrency(homePrice - costPerHome)}/unit supports {roiStr} ROI across {units} units.
          </p>
        ) : profit <= 0 ? (
          <p className="text-rose-200">
            <strong>Why this doesn{"'"}t work:</strong> Total cost ({formatCurrency(cost)}) exceeds revenue ({formatCurrency(revenue)}).
            {units <= 2 ? " The parcel produces too few units to absorb fixed costs (land, infrastructure)." : ""}
            {costPerHome > homePrice ? " Construction cost per home exceeds the projected sale price." : ""}
          </p>
        ) : null}

        {run.zoning_bypassed ? (
          <p className="text-amber-300">
            Zoning uses fallback rules — not backed by a real GIS overlay. Layout and density assumptions may not reflect actual entitlements.
          </p>
        ) : null}
        <p className="text-xs text-slate-500">
          {calSource?.includes("internal") ? "Revenue and cost calibrated from Flagship Homes closed deals." : "Construction costs use regional proxy data."}{" "}
          This memo is for screening purposes.
        </p>
      </div>
    </div>
  );
}

function RecommendationBanner({
  deal,
  run,
  nearFeasible,
  optDecision,
}: {
  deal: DealRecord | null;
  run: PipelineRun;
  nearFeasible: NearFeasibleResult | null | undefined;
  optDecision: OptimizationDecision | null;
}) {
  const status = deal?.status ?? "PASS";
  const recommendation = optDecision?.rationale ?? optDecision?.reason ?? buildRecommendation(status, run, nearFeasible);

  const toneMap: Record<DealStatus, { border: string; bg: string; text: string; label: string }> = {
    STRONG: {
      border: "border-emerald-400/40",
      bg: "bg-emerald-400/8",
      text: "text-emerald-100",
      label: "Strong opportunity",
    },
    MARGINAL: {
      border: "border-amber-400/40",
      bg: "bg-amber-400/8",
      text: "text-amber-100",
      label: "Marginal — review before proceeding",
    },
    PASS: {
      border: "border-rose-400/40",
      bg: "bg-rose-400/8",
      text: "text-rose-100",
      label: "Pass — does not meet thresholds",
    },
    NEAR_FEASIBLE: {
      border: "border-violet-400/40",
      bg: "bg-violet-400/8",
      text: "text-violet-100",
      label: "Near feasible — conditional upside",
    },
  };

  const tone = toneMap[status];

  return (
    <div className={`rounded-[28px] border ${tone.border} ${tone.bg} p-6`}>
      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge status={status} />
        <PipelineBadge pipelineStatus={run.status} />
        {optDecision ? (
          <span className="inline-flex rounded-full border border-cyan-400/40 bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            {optDecision.recommendation.replace(/_/g, " ")}
          </span>
        ) : null}
      </div>
      <h2 className={`mt-3 text-xl font-semibold ${tone.text}`}>
        {optDecision ? `Recommendation: ${optDecision.recommendation.replace(/_/g, " ")}` : tone.label}
      </h2>
      <p className={`mt-2 text-sm leading-7 ${tone.text} opacity-80`}>{recommendation}</p>
      {optDecision?.alternative ? (
        <p className={`mt-1 text-sm leading-7 ${tone.text} opacity-60`}>
          Alternative: {optDecision.alternative}
        </p>
      ) : null}
      {optDecision?.target_price != null ? (
        <div className="mt-3 inline-flex rounded-full border border-emerald-400/30 bg-emerald-400/8 px-4 py-1.5 text-sm font-semibold text-emerald-200">
          Recommended max offer: {formatCurrency(optDecision.target_price)}
        </div>
      ) : null}
    </div>
  );
}

function SummaryMetrics({
  deal,
  feasibility,
  run,
  optDecision,
}: {
  deal: DealRecord | null;
  feasibility: BedrockFeasibilityResult | null;
  run: PipelineRun;
  optDecision: OptimizationDecision | null;
}) {
  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        Summary metrics
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Units" value={formatInteger(deal?.units)} />
        <Metric label="ROI" value={formatPercent(deal?.roi)} />
        <Metric label="Projected profit" value={formatCurrency(feasibility?.projected_profit ?? deal?.projected_profit)} />
        <Metric label="Confidence" value={formatPercent(feasibility?.confidence_score ?? feasibility?.confidence ?? deal?.confidence)} />
        <Metric label="Revenue" value={formatCurrency(feasibility?.projected_revenue)} />
        <Metric label="Total cost" value={formatCurrency(feasibility?.projected_cost)} />
        <Metric label="Cost per unit" value={formatCurrency(feasibility?.cost_per_unit)} />
        <Metric label="Revenue per unit" value={formatCurrency(feasibility?.revenue_per_unit)} />
      </div>
    </div>
  );
}

function ConfidenceBreakdown({ feasibility }: { feasibility: BedrockFeasibilityResult | null }) {
  const breakdown = (feasibility?.financial_summary as Record<string, unknown> | undefined)?.confidence_breakdown as Record<string, number> | undefined;
  if (!breakdown) return null;

  const components = [
    { key: "market_data_quality", label: "Market data quality" },
    { key: "zoning_source_quality", label: "Zoning source quality" },
    { key: "cost_model_calibration", label: "Cost model calibration" },
    { key: "layout_feasibility", label: "Layout feasibility" },
  ];

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        Confidence breakdown
      </div>
      <p className="mt-2 text-sm leading-7 text-slate-400">
        Where certainty is strong and where it degrades.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {components.map(({ key, label }) => {
          const value = breakdown[key];
          if (typeof value !== "number") return null;
          const pct = Math.round(value * 100);
          const tone = pct >= 90 ? "text-emerald-300" : pct >= 70 ? "text-amber-300" : "text-rose-300";
          return (
            <div key={key} className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-4">
              <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
              <div className={`mt-2 text-lg font-semibold ${tone}`}>{pct}%</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AssumptionCard({
  feasibility,
  run,
}: {
  feasibility: BedrockFeasibilityResult | null;
  run: PipelineRun;
}) {
  const fs = feasibility?.financial_summary as Record<string, unknown> | undefined;
  const mc = fs?.market_context as Record<string, unknown> | undefined;
  const assumptions = feasibility?.assumptions as Record<string, unknown> | undefined;
  const devBreakdown = fs?.development_cost_breakdown as Record<string, number> | undefined;

  if (!mc) return null;

  const jurisdiction = mc.jurisdiction as string | undefined;
  const median = mc.median_home_value as number | undefined;
  const pricingProxy = mc.pricing_proxy as string | undefined;
  const costProxy = mc.cost_proxy as string | undefined;
  const usedCountyFallback = Boolean(mc.used_county_fallback);
  const costPerSqft = mc.construction_cost_per_sqft as number | undefined;
  const rpp = mc.rpp_all_items as number | undefined;
  const landShare = mc.land_value_share_of_home_value as number | undefined;
  const homeSize = mc.estimated_home_size_sqft as number | undefined;

  const zoningBypassed = run.zoning_bypassed;
  const zoningDistrict = run.zoning_result?.district;

  type QualityLevel = "strong" | "moderate" | "weak";
  const revenueQuality: QualityLevel = usedCountyFallback ? "moderate" : median ? "strong" : "weak";
  const zoningQuality: QualityLevel = zoningBypassed ? "weak" : "strong";
  const costQuality: QualityLevel = "moderate";

  const qualityColors: Record<QualityLevel, string> = {
    strong: "border-emerald-400/30 bg-emerald-400/8 text-emerald-200",
    moderate: "border-amber-400/30 bg-amber-400/8 text-amber-200",
    weak: "border-rose-400/30 bg-rose-400/8 text-rose-200",
  };
  const qualityLabels: Record<QualityLevel, string> = {
    strong: "Jurisdiction-specific",
    moderate: "Regional proxy",
    weak: "Default / fallback",
  };

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        How these numbers were computed
      </div>
      <div className="mt-4 space-y-3">
        <div className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Revenue basis</div>
            <span className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${qualityColors[revenueQuality]}`}>
              {qualityLabels[revenueQuality]}
            </span>
          </div>
          <div className="mt-2 text-sm text-slate-200">
            {median ? `Median home value for ${jurisdiction}: ${formatCurrency(median)}` : "Default pricing ($480,000)"}
          </div>
          {usedCountyFallback ? (
            <div className="mt-1 text-xs text-amber-300">County-level fallback — no jurisdiction-specific data</div>
          ) : null}
          <div className="mt-1 text-xs text-slate-500">Source: {pricingProxy?.replace(/_/g, " ") ?? "unknown"}</div>
        </div>

        <div className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Cost basis</div>
            <span className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${qualityColors[costQuality]}`}>
              {qualityLabels[costQuality]}
            </span>
          </div>
          <div className="mt-2 text-sm text-slate-200">
            {costPerSqft ? `$${costPerSqft.toFixed(0)}/sqft × ${homeSize?.toLocaleString() ?? "2,000"} sqft reference home` : "National baseline"}
            {rpp ? ` (RPP ${rpp.toFixed(1)})` : ""}
          </div>
          <div className="mt-1 text-xs text-slate-500">Source: {costProxy?.replace(/_/g, " ") ?? "national baseline"}</div>
        </div>

        <div className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Zoning basis</div>
            <span className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${qualityColors[zoningQuality]}`}>
              {qualityLabels[zoningQuality]}
            </span>
          </div>
          <div className="mt-2 text-sm text-slate-200">
            District: {zoningDistrict ?? "Unknown"}
            {zoningBypassed ? " (exploratory — not overlay-backed)" : " (real overlay)"}
          </div>
        </div>

        <div className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Land basis</div>
          <div className="mt-2 text-sm text-slate-200">
            {landShare ? `${(landShare * 100).toFixed(0)}% of home value × parcel acreage` : "18% of home value × acreage"}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            This is a proxy. Actual land acquisition price may vary significantly.
          </div>
        </div>

        {devBreakdown ? (
          <div className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Development cost breakdown</div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
              {Object.entries(devBreakdown).map(([key, val]) => (
                <div key={key}>
                  <span className="text-slate-500">{key}:</span>{" "}
                  <span className="text-slate-200">{formatCurrency(val)}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function WhySection({
  deal,
  feasibility,
  run,
  nearFeasible,
  optDecision,
}: {
  deal: DealRecord | null;
  feasibility: BedrockFeasibilityResult | null;
  run: PipelineRun;
  nearFeasible: NearFeasibleResult | null | undefined;
  optDecision: OptimizationDecision | null;
}) {
  const reasons = buildWhyReasons(deal, feasibility, run, nearFeasible);

  if (optDecision?.key_risks?.length) {
    reasons.push({
      label: "Key risks (optimization)",
      value: optDecision.key_risks.join(", "),
    });
  }
  if (optDecision?.sensitivity?.length) {
    reasons.push({
      label: "Sensitivity factors",
      value: optDecision.sensitivity.join(", "),
    });
  }

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        Why this deal {deal?.status === "STRONG" ? "works" : "does not work"}
      </div>
      <div className="mt-4 space-y-3">
        {reasons.length ? (
          reasons.map((reason, index) => (
            <div
              key={index}
              className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3"
            >
              <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{reason.label}</div>
              <div className="mt-1 text-sm text-slate-200">{reason.value}</div>
            </div>
          ))
        ) : (
          <div className="text-sm text-slate-500">No detailed reason data available for this run.</div>
        )}
      </div>
    </div>
  );
}

function SensitivitySection({
  feasibility,
  optDecision,
}: {
  feasibility: BedrockFeasibilityResult | null;
  optDecision: OptimizationDecision | null;
}) {
  const roiWorst = optDecision?.expected_roi_worst_case ?? feasibility?.ROI_worst_case;
  const roiBase = optDecision?.expected_roi_base ?? feasibility?.ROI_base ?? feasibility?.ROI;
  const roiBest = optDecision?.expected_roi_best_case ?? feasibility?.ROI_best_case;
  const hasRange = roiBest != null || roiWorst != null || feasibility?.break_even_price != null;

  if (!hasRange) return null;

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        Sensitivity range
      </div>
      <p className="mt-2 text-sm leading-7 text-slate-400">
        How the deal changes under different assumptions.
        {optDecision ? " Values from optimization analysis." : ""}
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Metric label="ROI worst case" value={formatPercent(roiWorst)} />
        <Metric label="ROI base" value={formatPercent(roiBase)} highlight />
        <Metric label="ROI best case" value={formatPercent(roiBest)} />
      </div>
      {feasibility?.break_even_price != null ? (
        <div className="mt-3">
          <Metric label="Break-even home price" value={formatCurrency(feasibility.break_even_price)} />
        </div>
      ) : null}
    </div>
  );
}

function BreakpointSection({ breakpoints }: { breakpoints: SensitivityBreakpoint[] }) {
  return (
    <div className="rounded-[28px] border border-cyan-400/20 bg-cyan-400/5 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-300">
        Breakpoint analysis
      </div>
      <p className="mt-2 text-sm leading-7 text-slate-400">
        How far each variable can move before the deal breaks.
      </p>
      <div className="mt-4 space-y-3">
        {breakpoints.map((bp, idx) => (
          <div key={idx} className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
                {bp.variable.replace(/_/g, " ")}
              </div>
              {bp.margin_percent != null ? (
                <span className={`text-xs font-semibold ${Math.abs(bp.margin_percent) < 10 ? "text-amber-300" : "text-emerald-300"}`}>
                  {bp.margin_percent > 0 ? "+" : ""}{bp.margin_percent.toFixed(1)}% margin
                </span>
              ) : null}
            </div>
            <div className="mt-2 grid gap-2 sm:grid-cols-3 text-sm">
              <div><span className="text-slate-500">Current:</span> <span className="text-slate-200">{formatBreakpointValue(bp.variable, bp.current_value)}</span></div>
              <div><span className="text-slate-500">Break-even:</span> <span className="text-slate-200">{formatBreakpointValue(bp.variable, bp.break_even_value)}</span></div>
              {bp.margin_value != null ? (
                <div><span className="text-slate-500">Margin:</span> <span className="text-slate-200">{formatBreakpointValue(bp.variable, bp.margin_value)}</span></div>
              ) : null}
            </div>
            <div className="mt-2 text-xs text-slate-400">{bp.explanation}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EconomicScenariosSection({ scenarios }: { scenarios: EconomicScenario[] }) {
  const evaluated = scenarios.filter((s) => s.status === "evaluated");
  if (!evaluated.length) return null;

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        Economic scenarios
      </div>
      <p className="mt-2 text-sm leading-7 text-slate-400">
        What happens under different market and regulatory conditions.
      </p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {evaluated.map((scenario) => (
          <div key={scenario.scenario_name} className="rounded-[20px] border border-slate-800 bg-slate-950/70 p-4">
            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
              {scenario.scenario_type.replace(/_/g, " ")}
            </div>
            <div className="mt-2 text-sm font-semibold text-slate-100">{scenario.scenario_name}</div>
            <div className="mt-3 space-y-1 text-sm">
              {scenario.best_roi != null ? (
                <div><span className="text-slate-500">Best ROI:</span> <span className="text-slate-200">{formatPercent(scenario.best_roi)}</span></div>
              ) : null}
              {scenario.delta_roi != null ? (
                <div><span className="text-slate-500">ROI delta:</span> <span className={scenario.delta_roi > 0 ? "text-emerald-300" : "text-rose-300"}>{scenario.delta_roi > 0 ? "+" : ""}{formatPercent(scenario.delta_roi)}</span></div>
              ) : null}
              {scenario.best_projected_profit != null ? (
                <div><span className="text-slate-500">Best profit:</span> <span className="text-slate-200">{formatCurrency(scenario.best_projected_profit)}</span></div>
              ) : null}
              {scenario.recommended_max_offer_price != null ? (
                <div className="mt-2 rounded-lg border border-emerald-400/20 bg-emerald-400/5 px-3 py-2">
                  <span className="text-emerald-200 font-semibold">Max offer: {formatCurrency(scenario.recommended_max_offer_price)}</span>
                </div>
              ) : null}
            </div>
            {scenario.explanation ? (
              <div className="mt-3 text-xs text-slate-400">{scenario.explanation}</div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function CandidateSensitivitySection({ analysis }: { analysis: CandidateSensitivity[] }) {
  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        Candidate sensitivity
      </div>
      <div className="mt-4 space-y-4">
        {analysis.map((candidate) => (
          <div key={candidate.layout_id} className="rounded-[20px] border border-slate-800 bg-slate-950/70 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-xs font-mono text-slate-400">{candidate.layout_id}</span>
              <span className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${
                candidate.status === "best_candidate"
                  ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
                  : candidate.status === "near_feasible"
                    ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
                    : "border-rose-400/40 bg-rose-400/10 text-rose-300"
              }`}>
                {candidate.status.replace(/_/g, " ")}
              </span>
            </div>
            <div className="mt-2 text-sm text-slate-300">{candidate.make_it_work_statement}</div>
            <div className="mt-2 text-xs text-slate-500">
              Margin to feasibility: {formatPercent(candidate.margin_to_feasibility)} | Primary failure: {candidate.primary_failure_reason.replace(/_/g, " ")}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function NearFeasibleSection({
  nearFeasible,
  run,
}: {
  nearFeasible: NearFeasibleResult;
  run: PipelineRun;
}) {
  return (
    <div className="rounded-[28px] border border-violet-400/20 bg-violet-400/5 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-violet-300">
        Near-feasible analysis
      </div>
      <h3 className="mt-2 text-lg font-semibold text-slate-100">
        What would need to change
      </h3>

      <div className="mt-4 space-y-4">
        <ReportBlock
          title="Limiting constraints"
          entries={objectToEntries(nearFeasible.limiting_constraints)}
          emptyLabel="No limiting constraints returned."
        />
        <ReportBlock
          title="Required relaxation"
          entries={objectToRelaxationEntries(nearFeasible.required_relaxation)}
          emptyLabel="No relaxation data returned."
        />
        <ReportBlock
          title="Best attempt summary"
          entries={objectToEntries(nearFeasible.best_attempt_summary)}
          emptyLabel="No best attempt data returned."
        />
        {nearFeasible.financial_upside ? (
          <ReportBlock
            title="Financial upside if resolved"
            entries={objectToEntries(nearFeasible.financial_upside)}
            emptyLabel="No upside estimate returned."
          />
        ) : null}
        {nearFeasible.attempted_strategies.length ? (
          <div className="rounded-[20px] border border-slate-800 bg-slate-950/50 px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
              Attempted strategies
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {nearFeasible.attempted_strategies.map((s) => (
                <span
                  key={s}
                  className="rounded-full border border-slate-700 px-3 py-1 text-xs font-medium text-slate-200"
                >
                  {s.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function NextActions({
  deal,
  run,
  parcelId,
  nearFeasible,
  optDecision,
}: {
  deal: DealRecord | null;
  run: PipelineRun;
  parcelId: string;
  nearFeasible: NearFeasibleResult | null | undefined;
  optDecision: OptimizationDecision | null;
}) {
  const actions = optDecision
    ? buildNextActionsFromDecision(optDecision, parcelId)
    : buildNextActions(deal?.status ?? "PASS", nearFeasible);

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        Recommended next actions
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {actions.map((action) => (
          <div
            key={action.label}
            className={`rounded-[20px] border px-5 py-4 ${action.primary
              ? "border-emerald-400/40 bg-emerald-400/10"
              : "border-slate-800 bg-slate-950/70"
              }`}
          >
            <div
              className={`text-sm font-semibold ${action.primary ? "text-emerald-200" : "text-slate-200"}`}
            >
              {action.label}
            </div>
            <div className="mt-1 text-xs leading-5 text-slate-400">{action.description}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecordDecisionPanel({
  parcelId,
  optimizationRunId,
  pipelineRunId,
  systemRecommendation,
  targetPrice,
  existingDecision,
}: {
  parcelId: string;
  optimizationRunId: string | null;
  pipelineRunId: string;
  systemRecommendation: string | null;
  targetPrice: number | null;
  existingDecision: import("@/lib/parcels").DecisionRecord | null;
}) {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [selectedAction, setSelectedAction] = useState<string>(
    existingDecision?.user_action ?? ""
  );

  if (existingDecision) {
    const statusTone =
      existingDecision.status === "decided" || existingDecision.status === "in_progress"
        ? "border-emerald-400/30 bg-emerald-400/8 text-emerald-200"
        : existingDecision.status === "abandoned"
          ? "border-rose-400/30 bg-rose-400/8 text-rose-200"
          : "border-slate-700 bg-slate-900/70 text-slate-300";

    return (
      <div className={`rounded-[28px] border p-6 ${statusTone}`}>
        <div className="text-[11px] font-semibold uppercase tracking-[0.28em] opacity-60">
          Decision recorded
        </div>
        <div className="mt-2 text-lg font-semibold">
          {existingDecision.user_action?.replace(/_/g, " ") ?? existingDecision.status}
        </div>
        {existingDecision.notes ? (
          <p className="mt-2 text-sm opacity-70">{existingDecision.notes}</p>
        ) : null}
        <div className="mt-3 text-xs opacity-50">
          Recorded {new Date(existingDecision.updated_at).toLocaleDateString()}
        </div>
      </div>
    );
  }

  const actionOptions = [
    { value: "acquire", label: "Acquire" },
    { value: "pass", label: "Pass" },
    { value: "hold", label: "Hold for review" },
    { value: "renegotiate", label: "Renegotiate" },
    { value: "rezoning_in_progress", label: "Pursue rezoning" },
  ];

  async function handleRecord() {
    if (!selectedAction) return;
    setSaving(true);
    try {
      await createDecision({
        parcel_id: parcelId,
        optimization_run_id: optimizationRunId,
        pipeline_run_id: pipelineRunId,
        system_recommendation: systemRecommendation,
        user_action: selectedAction,
        target_price: targetPrice,
      });
      setSaved(true);
      await queryClient.invalidateQueries({ queryKey: ["report-decisions", parcelId] });
      await queryClient.invalidateQueries({ queryKey: ["decisions"] });
    } catch {
      setSaving(false);
    }
  }

  if (saved) {
    return (
      <div className="rounded-[28px] border border-emerald-400/30 bg-emerald-400/8 p-6">
        <div className="text-sm font-semibold text-emerald-200">
          Decision recorded: {selectedAction.replace(/_/g, " ")}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        Record your decision
      </div>
      <p className="mt-2 text-sm leading-7 text-slate-400">
        Select an action to persist this decision to the deal pipeline.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {actionOptions.map((option) => (
          <button
            key={option.value}
            onClick={() => setSelectedAction(option.value)}
            className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
              selectedAction === option.value
                ? "border-cyan-400 bg-cyan-400/10 text-cyan-200"
                : "border-slate-700 text-slate-300 hover:border-slate-500"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
      <button
        onClick={() => void handleRecord()}
        disabled={!selectedAction || saving}
        className="mt-4 rounded-2xl bg-cyan-400 px-5 py-3 text-sm font-semibold uppercase tracking-[0.22em] text-slate-950 disabled:opacity-50"
      >
        {saving ? "Saving..." : "Record decision"}
      </button>
    </div>
  );
}

function NavigationFooter({ parcelId, run }: { parcelId: string; run: PipelineRun }) {
  return (
    <div className="flex flex-wrap gap-3">
      <Link
        href={`/studio/${parcelId}`}
        className="rounded-2xl border border-slate-700 bg-slate-900/70 px-5 py-3 text-sm font-semibold text-slate-200 transition hover:border-slate-500"
      >
        Open in Studio for geometry inspection
      </Link>
      <Link
        href={`/runs/${run.run_id}`}
        className="rounded-2xl border border-slate-700 bg-slate-900/70 px-5 py-3 text-sm font-semibold text-slate-200 transition hover:border-slate-500"
      >
        View full pipeline run
      </Link>
      <Link
        href="/opportunities"
        className="rounded-2xl border border-slate-700 bg-slate-900/70 px-5 py-3 text-sm font-semibold text-slate-200 transition hover:border-slate-500"
      >
        Back to Opportunities
      </Link>
    </div>
  );
}

function Metric({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-[20px] border px-4 py-4 ${highlight ? "border-cyan-400/30 bg-cyan-400/5" : "border-slate-800 bg-slate-950/70"
        }`}
    >
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-2 text-lg font-semibold text-slate-100">{value}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: DealStatus }) {
  const tones: Record<DealStatus, string> = {
    STRONG: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
    MARGINAL: "border-amber-400/40 bg-amber-400/10 text-amber-300",
    PASS: "border-rose-400/40 bg-rose-400/10 text-rose-300",
    NEAR_FEASIBLE: "border-violet-400/40 bg-violet-400/10 text-violet-300",
  };

  return (
    <span
      className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${tones[status]}`}
    >
      {status === "NEAR_FEASIBLE" ? "Near feasible" : status}
    </span>
  );
}

function PipelineBadge({ pipelineStatus }: { pipelineStatus: string }) {
  return (
    <span className="inline-flex rounded-full border border-slate-700 bg-slate-900/70 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">
      {pipelineStatus.replace(/_/g, " ")}
    </span>
  );
}

function ReportBlock({
  title,
  entries,
  emptyLabel,
}: {
  title: string;
  entries: Array<{ label: string; value: string }>;
  emptyLabel: string;
}) {
  return (
    <div className="rounded-[20px] border border-slate-800 bg-slate-950/50 px-4 py-3">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{title}</div>
      {entries.length ? (
        <dl className="mt-3 space-y-2">
          {entries.map((entry) => (
            <div
              key={entry.label}
              className="flex flex-wrap items-start justify-between gap-2 rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-2"
            >
              <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                {entry.label}
              </dt>
              <dd className="text-sm text-slate-200">{entry.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <div className="mt-2 text-sm text-slate-500">{emptyLabel}</div>
      )}
    </div>
  );
}

// --- helpers ---

function formatBreakpointValue(variable: string, value: number | null | undefined): string {
  if (value == null) return "\u2014";
  if (/price|cost|value|offer/i.test(variable)) return formatCurrency(value);
  if (/density|units/i.test(variable)) return value.toFixed(1);
  if (/roi/i.test(variable)) return formatPercent(value);
  return value.toLocaleString();
}

function buildNextActionsFromDecision(
  decision: OptimizationDecision,
  parcelId: string,
): Array<{ label: string; description: string; primary: boolean }> {
  const actions: Array<{ label: string; description: string; primary: boolean }> = [];

  if (decision.recommendation === "acquire") {
    actions.push({
      label: "Acquire",
      description: decision.target_price
        ? `Recommended max offer: ${formatCurrency(decision.target_price)}. Move to acquisition diligence.`
        : "This parcel passes optimization thresholds. Move to acquisition diligence and title review.",
      primary: true,
    });
  } else if (decision.recommendation === "renegotiate_price") {
    actions.push({
      label: "Renegotiate price",
      description: decision.target_price
        ? `Target a land basis at or below ${formatCurrency(decision.target_price)} to make this work.`
        : "The margin is thin. Negotiate a lower land cost or explore density upside.",
      primary: true,
    });
  } else if (decision.recommendation === "pursue_rezoning") {
    actions.push({
      label: "Pursue rezoning",
      description: "Current zoning is the binding constraint. Higher density through rezoning or a variance could unlock this parcel.",
      primary: true,
    });
  } else {
    actions.push({
      label: "Abandon",
      description: decision.reason ?? "This parcel does not meet thresholds under optimization analysis.",
      primary: true,
    });
  }

  if (decision.recommendation !== "abandon") {
    actions.push({
      label: "Inspect in Studio",
      description: "Review the geometry and design iteration options before committing.",
      primary: false,
    });
  }

  if (decision.recommendation !== "acquire") {
    actions.push({
      label: decision.recommendation === "abandon" ? "Renegotiate" : "Abandon",
      description: decision.recommendation === "abandon"
        ? "Only revisit if market assumptions change materially."
        : "If the path to improvement is unclear, redirect acquisition effort.",
      primary: false,
    });
  }

  return actions;
}

function buildRecommendation(
  status: DealStatus,
  run: PipelineRun,
  nearFeasible: NearFeasibleResult | null | undefined
): string {
  if (status === "STRONG") {
    return "This parcel meets ROI and profit thresholds under current assumptions. It is ready for acquisition diligence.";
  }
  if (status === "MARGINAL") {
    return "This parcel is near the decision boundary. Small changes in home price or construction cost could move it to strong or pass. Review the sensitivity range before committing.";
  }
  if (status === "NEAR_FEASIBLE") {
    const reason = nearFeasible?.reason_category?.replace(/_/g, " ") ?? "constraint limitations";
    return `This parcel did not complete the standard pipeline due to ${reason}. It may have conditional upside if the limiting constraint is addressed through variance, rezoning, or geometry correction.`;
  }
  return "This parcel does not meet the minimum ROI or profit thresholds under current assumptions. Consider abandoning or revisiting only if market conditions change significantly.";
}

function buildWhyReasons(
  deal: DealRecord | null,
  feasibility: BedrockFeasibilityResult | null,
  run: PipelineRun,
  nearFeasible: NearFeasibleResult | null | undefined
): Array<{ label: string; value: string }> {
  const reasons: Array<{ label: string; value: string }> = [];

  if (deal) {
    reasons.push({
      label: "Deal classification",
      value: `${deal.status} — ROI ${formatPercent(deal.roi)}, projected profit ${formatCurrency(deal.projected_profit)}`,
    });
  }

  if (feasibility) {
    if (feasibility.constraint_violations?.length) {
      reasons.push({
        label: "Constraint violations",
        value: feasibility.constraint_violations.map((v) => v.replace(/_/g, " ")).join(", "),
      });
    }
    if (feasibility.key_risk_factors?.length) {
      reasons.push({
        label: "Key risk factors",
        value: feasibility.key_risk_factors.map((f) => f.replace(/_/g, " ")).join(", "),
      });
    }
    if (feasibility.assumptions) {
      const mode = feasibility.assumptions.integration_mode;
      if (typeof mode === "string") {
        reasons.push({
          label: "Integration mode",
          value: mode,
        });
      }
    }
  }

  if (nearFeasible) {
    reasons.push({
      label: "Near-feasible reason",
      value: nearFeasible.reason_category.replace(/_/g, " "),
    });
  }

  if (run.zoning_bypassed) {
    reasons.push({
      label: "Zoning bypass",
      value: `Zoning was bypassed: ${run.bypass_reason?.replace(/_/g, " ") ?? "fallback rules applied"}`,
    });
  }

  reasons.push({
    label: "Zoning district",
    value: run.zoning_result.district,
  });

  if (run.layout_result) {
    reasons.push({
      label: "Layout outcome",
      value: `${run.layout_result.unit_count} units on ${formatNumber(run.layout_result.road_length_ft)} ft of road`,
    });
  }

  return reasons;
}

function buildNextActions(
  status: DealStatus,
  nearFeasible: NearFeasibleResult | null | undefined
): Array<{ label: string; description: string; primary: boolean }> {
  if (status === "STRONG") {
    return [
      {
        label: "Acquire",
        description: "This parcel passes current thresholds. Move to acquisition diligence and title review.",
        primary: true,
      },
      {
        label: "Inspect in Studio",
        description: "Open the geometry workspace to review the lot layout and confirm buildability before committing.",
        primary: false,
      },
    ];
  }

  if (status === "MARGINAL") {
    return [
      {
        label: "Renegotiate",
        description: "The deal is close but sensitive. Explore lower land cost or higher density to improve ROI.",
        primary: true,
      },
      {
        label: "Pursue rezoning",
        description: "If density is the constraint, a zoning variance or overlay change could push this to strong.",
        primary: false,
      },
      {
        label: "Inspect in Studio",
        description: "Review the layout to see if design changes improve unit yield without rezoning.",
        primary: false,
      },
      {
        label: "Abandon",
        description: "If the margin is too thin and the path to improvement is unclear, move on.",
        primary: false,
      },
    ];
  }

  if (status === "NEAR_FEASIBLE") {
    const hasVariancePlay = nearFeasible
      ? Object.keys(nearFeasible.required_relaxation ?? {}).some((k) =>
        /setback|frontage|height|coverage|lot_area|min_lot/i.test(k)
      )
      : false;

    const actions: Array<{ label: string; description: string; primary: boolean }> = [];

    if (hasVariancePlay) {
      actions.push({
        label: "Pursue rezoning or variance",
        description: "The parcel is blocked by a specific dimensional standard. A variance or zone change could unlock it.",
        primary: true,
      });
    } else {
      actions.push({
        label: "Investigate constraint",
        description: "Understand the blocking constraint before committing resources. The path forward is not yet clear.",
        primary: true,
      });
    }

    actions.push({
      label: "Inspect in Studio",
      description: "Review the geometry to determine if the constraint is addressable through design iteration.",
      primary: false,
    });
    actions.push({
      label: "Abandon",
      description: "If the entitlement risk is too high or the upside is insufficient, do not pursue.",
      primary: false,
    });

    return actions;
  }

  return [
    {
      label: "Abandon",
      description: "This parcel does not meet thresholds. Redirect acquisition effort to stronger candidates.",
      primary: true,
    },
    {
      label: "Renegotiate",
      description: "Only revisit if land cost or market assumptions change materially.",
      primary: false,
    },
  ];
}

function objectToEntries(data: Record<string, unknown>): Array<{ label: string; value: string }> {
  return Object.entries(data ?? {}).map(([key, value]) => ({
    label: humanizeKey(key),
    value: formatMixedValue(key, value),
  }));
}

function objectToRelaxationEntries(data: Record<string, unknown>): Array<{ label: string; value: string }> {
  return Object.entries(data ?? {}).map(([key, value]) => {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const record = value as Record<string, unknown>;
      const parts = [
        `current ${formatScalar(record.current)}`,
        `needed ${formatScalar(record.needed)}`,
      ];
      const reduction = record.reduction_sqft ?? record.reduction_ft ?? record.reduction;
      if (reduction != null && reduction !== 0) {
        parts.push(`change ${formatScalar(reduction)}`);
      }
      return { label: humanizeKey(key), value: parts.join(" · ") };
    }
    return { label: humanizeKey(key), value: formatMixedValue(key, value) };
  });
}

function formatMixedValue(key: string, value: unknown): string {
  if (typeof value === "number") {
    if (/roi/i.test(key)) return `${(value * 100).toFixed(1)}%`;
    if (/profit|revenue|cost|price|value/i.test(key)) return formatCurrency(value);
    if (/sqft|area/i.test(key)) return `${Math.round(value).toLocaleString()} sqft`;
    if (/frontage|setback|height|length|width|ft/i.test(key)) return `${value.toFixed(1)} ft`;
  }
  return formatScalar(value);
}

function formatScalar(value: unknown): string {
  if (value == null) return "\u2014";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return String(value);
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.length ? value.map(formatScalar).join(", ") : "\u2014";
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim();
}

function formatCurrency(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "\u2014";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "\u2014";
  return `${(value * 100).toFixed(1)}%`;
}

function formatInteger(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "\u2014";
  return value.toLocaleString();
}

function formatNumber(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "\u2014";
  return Math.round(value).toLocaleString();
}
