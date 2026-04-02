"use client";

import type { BedrockFeasibilityResult, OptimizationDecision, OptimizationRun } from "@/lib/parcels";

export type ScenarioRow = {
  name: string;
  homePrice: number | null;
  costPerHome: number | null;
  landBasis: number | null;
  units: number | null;
  roi: number | null;
  profit: number | null;
  source: "base" | "sensitivity" | "economic_scenario" | "user_override";
};

export function ScenarioTable({
  feasibility,
  optDecision,
  optimizationRun,
  inferredAnalysis,
  userScenarios,
}: {
  feasibility: BedrockFeasibilityResult | null;
  optDecision: OptimizationDecision | null;
  optimizationRun: OptimizationRun | null;
  inferredAnalysis: { estimated_units_mid?: number; price_per_unit?: number; cost_per_unit?: number; roi?: number; projected_profit?: number } | null;
  userScenarios: ScenarioRow[];
}) {
  const rows: ScenarioRow[] = [];

  // Base case
  const baseUnits = feasibility?.units ?? inferredAnalysis?.estimated_units_mid ?? null;
  const basePrice = feasibility?.estimated_home_price ?? inferredAnalysis?.price_per_unit ?? null;
  const baseCost = feasibility?.construction_cost_per_home ?? inferredAnalysis?.cost_per_unit ?? null;
  const baseRoi = feasibility?.ROI_base ?? feasibility?.ROI ?? inferredAnalysis?.roi ?? null;
  const baseProfit = feasibility?.projected_profit ?? inferredAnalysis?.projected_profit ?? null;
  const fs = feasibility?.financial_summary as Record<string, unknown> | undefined;
  const mc = fs?.market_context as Record<string, unknown> | undefined;
  const baseLand = (mc?.land_price_estimate as number) ?? null;

  const baseRow: ScenarioRow | null =
    baseUnits || baseRoi !== null
      ? {
          name: "Base case",
          homePrice: basePrice,
          costPerHome: baseCost,
          landBasis: baseLand,
          units: baseUnits,
          roi: baseRoi,
          profit: baseProfit,
          source: "base",
        }
      : null;

  if (baseRow) rows.push(baseRow);

  // Conservative (worst case)
  const worstRoi = feasibility?.ROI_worst_case ?? (optDecision?.expected_roi_worst_case);
  if (worstRoi != null && basePrice != null && baseCost != null) {
    rows.push({
      name: "Conservative",
      homePrice: basePrice ? basePrice * 0.9 : null,
      costPerHome: baseCost ? baseCost * 1.08 : null,
      landBasis: baseLand,
      units: baseUnits,
      roi: worstRoi,
      profit: baseProfit != null && baseRoi != null && worstRoi != null
        ? baseProfit * (1 + worstRoi) / (1 + (baseRoi ?? 0.001)) * 0.85
        : null,
      source: "sensitivity",
    });
  }

  // Aggressive (best case)
  const bestRoi = feasibility?.ROI_best_case ?? (optDecision?.expected_roi_best_case);
  if (bestRoi != null && basePrice != null && baseCost != null) {
    rows.push({
      name: "Aggressive",
      homePrice: basePrice ? basePrice * 1.1 : null,
      costPerHome: baseCost ? baseCost * 0.92 : null,
      landBasis: baseLand,
      units: baseUnits,
      roi: bestRoi,
      profit: baseProfit != null && baseRoi != null && bestRoi != null
        ? baseProfit * (1 + bestRoi) / (1 + (baseRoi ?? 0.001)) * 1.15
        : null,
      source: "sensitivity",
    });
  }

  // Break-even
  const breakEven = feasibility?.break_even_price;
  if (breakEven != null) {
    rows.push({
      name: "Break-even",
      homePrice: breakEven,
      costPerHome: baseCost,
      landBasis: baseLand,
      units: baseUnits,
      roi: 0,
      profit: 0,
      source: "sensitivity",
    });
  }

  // User scenarios
  rows.push(...userScenarios);

  if (!rows.length) return null;

  const sourceTones: Record<string, string> = {
    base: "text-slate-100",
    sensitivity: "text-cyan-300",
    economic_scenario: "text-blue-300",
    user_override: "text-amber-300",
  };

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        Scenario comparison
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-[0.2em] text-slate-500">
              <th className="px-3 py-2">Scenario</th>
              <th className="px-3 py-2">Home Price</th>
              <th className="px-3 py-2">Cost/Home</th>
              <th className="px-3 py-2">Units</th>
              <th className="px-3 py-2">ROI</th>
              <th className="px-3 py-2">Profit</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const isBase = row.source === "base";
              return (
                <tr
                  key={`${row.name}-${i}`}
                  className={`border-t border-slate-800 ${isBase ? "bg-slate-950/50" : ""}`}
                >
                  <td className={`px-3 py-3 font-semibold ${sourceTones[row.source] ?? "text-slate-300"}`}>
                    {row.name}
                    {row.source === "user_override" ? (
                      <span className="ml-1 text-[9px] uppercase text-amber-400/60">custom</span>
                    ) : row.source === "sensitivity" ? (
                      <span className="ml-1 text-[9px] uppercase text-cyan-400/60">pre-computed</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-3 text-slate-300">
                    {fmtCurrency(row.homePrice)}
                    {!isBase && <DeltaCurrency value={row.homePrice} base={baseRow?.homePrice} />}
                  </td>
                  <td className="px-3 py-3 text-slate-300">
                    {fmtCurrency(row.costPerHome)}
                    {!isBase && <DeltaCurrency value={row.costPerHome} base={baseRow?.costPerHome} invertColor />}
                  </td>
                  <td className="px-3 py-3 text-slate-300">
                    {row.units?.toLocaleString() ?? "—"}
                    {!isBase && <DeltaInteger value={row.units} base={baseRow?.units} />}
                  </td>
                  <td className={`px-3 py-3 font-semibold ${roiColor(row.roi)}`}>
                    {fmtPercent(row.roi)}
                    {!isBase && <DeltaPercent value={row.roi} base={baseRow?.roi} />}
                  </td>
                  <td className="px-3 py-3 text-slate-300">
                    {fmtCurrency(row.profit)}
                    {!isBase && <DeltaCurrency value={row.profit} base={baseRow?.profit} />}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Delta display components ── */

function deltaColor(delta: number, invert = false) {
  const effective = invert ? -delta : delta;
  if (effective > 0) return "text-emerald-400";
  if (effective < 0) return "text-rose-400";
  return "text-slate-500";
}

function deltaArrow(delta: number, invert = false) {
  const effective = invert ? -delta : delta;
  if (effective > 0) return "\u2191";
  if (effective < 0) return "\u2193";
  return "";
}

function DeltaCurrency({
  value,
  base,
  invertColor = false,
}: {
  value: number | null | undefined;
  base: number | null | undefined;
  invertColor?: boolean;
}) {
  if (value == null || base == null || Number.isNaN(value) || Number.isNaN(base)) return null;
  const delta = value - base;
  if (delta === 0) return null;
  const sign = delta > 0 ? "+" : "";
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(delta);
  return (
    <div className={`text-[11px] leading-tight ${deltaColor(delta, invertColor)}`}>
      {deltaArrow(delta, invertColor)} {sign}{formatted} <span className="text-white/30">vs base</span>
    </div>
  );
}

function DeltaPercent({
  value,
  base,
}: {
  value: number | null | undefined;
  base: number | null | undefined;
}) {
  if (value == null || base == null || Number.isNaN(value) || Number.isNaN(base)) return null;
  const delta = value - base;
  if (Math.abs(delta) < 0.0001) return null;
  const sign = delta > 0 ? "+" : "";
  return (
    <div className={`text-[11px] leading-tight ${deltaColor(delta)}`}>
      {deltaArrow(delta)} {sign}{(delta * 100).toFixed(1)} pts <span className="text-white/30">vs base</span>
    </div>
  );
}

function DeltaInteger({
  value,
  base,
}: {
  value: number | null | undefined;
  base: number | null | undefined;
}) {
  if (value == null || base == null || Number.isNaN(value) || Number.isNaN(base)) return null;
  const delta = value - base;
  if (delta === 0) return null;
  const sign = delta > 0 ? "+" : "";
  return (
    <div className={`text-[11px] leading-tight ${deltaColor(delta)}`}>
      {deltaArrow(delta)} {sign}{delta.toLocaleString()} <span className="text-white/30">vs base</span>
    </div>
  );
}

/* ── Formatters ── */

function fmtCurrency(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(v);
}

function fmtPercent(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function roiColor(roi: number | null | undefined) {
  if (roi == null) return "text-slate-400";
  if (roi >= 0.15) return "text-emerald-300";
  if (roi >= 0) return "text-amber-300";
  return "text-rose-300";
}
