"use client";

import { useState } from "react";
import type { BedrockFeasibilityResult, BedrockLayoutResult } from "@/lib/parcels";
import { computeROI, solveDeal } from "@/lib/dealSolver";
import type { SolverResult } from "@/lib/dealSolver";

const DEFAULT_TARGET_ROI = 0.10;

export function DealSolver({
  feasibility,
  layoutResult,
  parcelAreaSqft,
}: {
  feasibility: BedrockFeasibilityResult | null;
  layoutResult: BedrockLayoutResult | null;
  parcelAreaSqft: number | null;
}) {
  const [results, setResults] = useState<SolverResult[] | null>(null);
  const [alreadyViable, setAlreadyViable] = useState(false);

  if (!feasibility || !layoutResult || !parcelAreaSqft) return null;

  const fs = feasibility.financial_summary as Record<string, unknown> | undefined;
  const mc = fs?.market_context as Record<string, unknown> | undefined;

  const currentHomePrice = feasibility.estimated_home_price;
  const currentCostPerHome = feasibility.construction_cost_per_home;
  const currentLandPrice = (mc?.land_price_estimate as number) ?? 0;
  const roadCostPerFt = (mc?.road_cost_per_ft as number) ?? 300;

  const units = feasibility.units;
  const roadLengthFt = layoutResult.road_length_ft;
  const utilityLengthFt = layoutResult.utility_length_ft ?? 0;

  function handleSolve() {
    // Check if already viable
    const baseResult = computeROI(
      currentHomePrice,
      currentCostPerHome,
      currentLandPrice,
      roadCostPerFt,
      { units, roadLengthFt, utilityLengthFt, parcelAreaSqft: parcelAreaSqft! },
    );

    if (baseResult.roi !== null && baseResult.roi >= DEFAULT_TARGET_ROI) {
      setAlreadyViable(true);
      setResults(null);
      return;
    }

    setAlreadyViable(false);
    const solved = solveDeal(
      {
        units,
        roadLengthFt,
        utilityLengthFt,
        parcelAreaSqft: parcelAreaSqft!,
        currentHomePrice,
        currentCostPerHome,
        currentLandPrice,
        roadCostPerFt,
      },
      DEFAULT_TARGET_ROI,
    );
    setResults(solved);
  }

  const achievable = results?.filter((r) => r.achievable) ?? [];
  const notAchievable = results?.filter((r) => !r.achievable) ?? [];

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        Make this deal work
      </div>
      <p className="mt-2 text-xs text-slate-400">
        Find the minimum single-variable change to reach {(DEFAULT_TARGET_ROI * 100).toFixed(0)}% ROI.
        Layout and unit count remain locked.
      </p>

      {!results && !alreadyViable ? (
        <button
          onClick={handleSolve}
          className="mt-4 rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950"
        >
          Make this deal work
        </button>
      ) : null}

      {alreadyViable ? (
        <div className="mt-4 rounded-[20px] border border-emerald-400/30 bg-emerald-400/5 px-4 py-3">
          <div className="text-sm font-semibold text-emerald-300">
            This deal already meets the {(DEFAULT_TARGET_ROI * 100).toFixed(0)}% ROI target
          </div>
          <div className="mt-1 text-xs text-slate-400">
            Base ROI is {fmtPercent(feasibility.ROI_base ?? feasibility.ROI)}. No adjustments needed.
          </div>
        </div>
      ) : null}

      {results && !alreadyViable ? (
        <div className="mt-4 space-y-3">
          {achievable.length === 0 ? (
            <div className="rounded-[20px] border border-rose-400/30 bg-rose-400/5 px-4 py-3">
              <div className="text-sm font-semibold text-rose-300">
                Cannot reach {(DEFAULT_TARGET_ROI * 100).toFixed(0)}% ROI within reasonable bounds
              </div>
              <div className="mt-1 text-xs text-slate-400">
                None of the three levers alone can bring this deal to the target.
              </div>
            </div>
          ) : null}

          {achievable.map((r, i) => (
            <ResultCard key={r.variable} result={r} rank={i} />
          ))}

          {notAchievable.map((r) => (
            <div
              key={r.variable}
              className="rounded-[20px] border border-rose-400/15 bg-rose-400/5 px-4 py-3"
            >
              <div className="text-xs font-semibold text-rose-300/70">
                Not achievable via {r.label}
              </div>
              <div className="mt-1 text-[11px] text-slate-500">
                Even at {r.variable === "home_price" ? "2x" : r.variable === "land_price" ? "$0" : "50%"} of current,
                ROI only reaches {fmtPercent(r.resultingRoi)}
              </div>
            </div>
          ))}

          <button
            onClick={() => { setResults(null); setAlreadyViable(false); }}
            className="mt-2 text-[11px] text-slate-500 hover:text-slate-300"
          >
            Reset
          </button>
        </div>
      ) : null}
    </div>
  );
}

function ResultCard({ result, rank }: { result: SolverResult; rank: number }) {
  const isBest = rank === 0;
  const direction = result.changePercent > 0 ? "Increase" : "Reduce";
  const arrow = result.changePercent > 0 ? "\u2191" : "\u2193";
  const borderClass = isBest
    ? "border-emerald-400/30 bg-emerald-400/5"
    : "border-slate-800 bg-slate-950/70";
  const labelClass = isBest ? "text-emerald-300" : "text-slate-500";

  return (
    <div className={`rounded-[20px] border px-4 py-3 ${borderClass}`}>
      <div className={`text-[10px] font-semibold uppercase tracking-[0.24em] ${labelClass}`}>
        {isBest ? "Best option" : "Alternative"}
      </div>
      <div className="mt-1 text-sm font-semibold text-slate-100">
        {arrow} {direction} {result.label} to {fmtCurrency(result.requiredValue)}{" "}
        <span className={`text-xs ${result.changePercent > 0 ? "text-emerald-400" : "text-rose-400"}`}>
          ({result.changePercent > 0 ? "+" : ""}{result.changePercent.toFixed(1)}%)
        </span>
      </div>
      <div className="mt-1 text-xs text-slate-400">
        {fmtPercent(result.resultingRoi)} ROI{" "}
        <span className="text-slate-600">&middot;</span>{" "}
        {fmtCurrency(result.resultingProfit)} profit
      </div>
    </div>
  );
}

function fmtCurrency(v: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(v);
}

function fmtPercent(v: number | null | undefined) {
  if (v == null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}
