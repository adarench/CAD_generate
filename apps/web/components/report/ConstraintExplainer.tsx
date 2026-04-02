"use client";

import type { BedrockFeasibilityResult, BedrockZoningRules, EconomicScenario, OptimizationDecision, SensitivityBreakpoint } from "@/lib/parcels";

export function ConstraintExplainer({
  feasibility,
  zoningResult,
  areaAcres,
  optDecision,
  economicScenarios,
}: {
  feasibility: BedrockFeasibilityResult | null;
  zoningResult: BedrockZoningRules | null;
  areaAcres: number;
  optDecision: OptimizationDecision | null;
  economicScenarios: EconomicScenario[];
}) {
  if (!feasibility && !zoningResult) return null;

  const units = feasibility?.units ?? 0;
  const density = zoningResult?.max_units_per_acre;
  const minLot = zoningResult?.min_lot_size_sqft;
  const district = zoningResult?.district ?? "Unknown";
  const theoreticalMax = density ? Math.floor(areaAcres * density) : null;
  const efficiency = theoreticalMax && theoreticalMax > 0 ? Math.round((units / theoreticalMax) * 100) : null;

  const fs = feasibility?.financial_summary as Record<string, unknown> | undefined;
  const mc = fs?.market_context as Record<string, unknown> | undefined;
  const costProxy = mc?.cost_proxy as string | undefined;
  const costSample = mc?.cost_sample_size as number | undefined;
  const pricingProxy = mc?.pricing_proxy as string | undefined;

  const breakpoints = optDecision?.breakpoints ?? [];
  const rezoning = economicScenarios.find((s) => s.scenario_type === "rezoning" && s.status === "evaluated");

  // Determine binding constraint
  let bindingConstraint = "Unknown";
  let bindingDetail = "";

  if (density && theoreticalMax && theoreticalMax <= units * 1.3) {
    bindingConstraint = "Zoning density";
    bindingDetail = `${district} allows max ${density} du/ac → ~${theoreticalMax} theoretical units on ${areaAcres.toFixed(1)} acres`;
  } else if (minLot && areaAcres * 43560 / minLot < units * 1.5) {
    bindingConstraint = "Minimum lot size";
    bindingDetail = `${district} requires ${minLot.toLocaleString()} sqft lots → ~${Math.floor(areaAcres * 43560 / minLot)} max lots`;
  } else {
    bindingConstraint = "Layout geometry";
    bindingDetail = "Road network, setbacks, and parcel shape limit buildable lots";
  }

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        Constraint analysis
      </div>

      <div className="mt-4 space-y-4">
        {/* Binding constraint */}
        <div className="rounded-[20px] border border-cyan-400/20 bg-cyan-400/5 px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-300">Binding constraint</div>
          <div className="mt-1 text-sm font-semibold text-slate-100">{bindingConstraint}</div>
          <div className="mt-1 text-sm text-slate-300">{bindingDetail}</div>
          {efficiency ? (
            <div className="mt-1 text-xs text-slate-400">
              Layout engine placed {units} lots ({efficiency}% of theoretical maximum)
            </div>
          ) : null}
        </div>

        {/* Cost basis */}
        <div className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Cost basis</div>
          <div className="mt-1 text-sm text-slate-300">
            {feasibility?.construction_cost_per_home
              ? `$${feasibility.construction_cost_per_home.toLocaleString()}/home`
              : "Unknown"}
            {costProxy?.includes("internal") ? ` (calibrated from ${costSample ?? 0} real deals)` : " (regional proxy)"}
          </div>
        </div>

        {/* Revenue basis */}
        <div className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Revenue basis</div>
          <div className="mt-1 text-sm text-slate-300">
            {feasibility?.estimated_home_price
              ? `$${feasibility.estimated_home_price.toLocaleString()}/home`
              : "Unknown"}
            {pricingProxy?.includes("internal") ? " (from closed deal data)" : " (Census ACS market median)"}
          </div>
        </div>

        {/* Breakpoints */}
        {breakpoints.length > 0 ? (
          <div className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Key breakpoints</div>
            <div className="mt-2 space-y-1">
              {breakpoints.map((bp, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">{bp.variable.replace(/_/g, " ")}</span>
                  <span className={`font-semibold ${bp.margin_percent && Math.abs(bp.margin_percent) < 10 ? "text-amber-300" : "text-slate-200"}`}>
                    {bp.margin_percent != null ? `${bp.margin_percent > 0 ? "+" : ""}${bp.margin_percent.toFixed(1)}% margin` : "—"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {/* Rezoning opportunity */}
        {rezoning && rezoning.best_roi != null ? (
          <div className="rounded-[20px] border border-emerald-400/20 bg-emerald-400/5 px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.24em] text-emerald-300">Rezoning opportunity</div>
            <div className="mt-1 text-sm text-slate-300">
              If density increased (e.g., {district} → higher-density zone):
              ROI improves to {(rezoning.best_roi * 100).toFixed(1)}%
              {rezoning.delta_roi != null ? ` (${rezoning.delta_roi > 0 ? "+" : ""}${(rezoning.delta_roi * 100).toFixed(1)} pts)` : ""}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
