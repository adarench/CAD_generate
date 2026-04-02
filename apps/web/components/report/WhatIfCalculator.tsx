"use client";

import { useState } from "react";
import { ensureBedrockParcel } from "@/lib/api";
import type { BedrockFeasibilityResult } from "@/lib/parcels";
import type { ScenarioRow } from "./ScenarioTable";

export function WhatIfCalculator({
  parcelId,
  feasibility,
  inferredAnalysis,
  onScenarioCreated,
}: {
  parcelId: string;
  feasibility: BedrockFeasibilityResult | null;
  inferredAnalysis: { price_per_unit?: number; cost_per_unit?: number; roi?: number; projected_profit?: number; estimated_units_mid?: number } | null;
  onScenarioCreated: (scenario: ScenarioRow) => void;
}) {
  const [field, setField] = useState<"land_price" | "estimated_home_price" | "construction_cost_per_home">("land_price");
  const [value, setValue] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fieldLabels = {
    land_price: "Land basis",
    estimated_home_price: "Home price",
    construction_cost_per_home: "Construction cost/home",
  };

  // Extract current baseline values from feasibility or inferred analysis
  const fs = feasibility?.financial_summary as Record<string, unknown> | undefined;
  const mc = fs?.market_context as Record<string, unknown> | undefined;

  const baseHomePrice = feasibility?.estimated_home_price ?? inferredAnalysis?.price_per_unit ?? 450000;
  const baseCostPerHome = feasibility?.construction_cost_per_home ?? inferredAnalysis?.cost_per_unit ?? 385000;
  const baseRoadCost = (mc?.road_cost_per_ft as number) ?? 300;
  const baseLandPrice = (mc?.land_price_estimate as number) ?? 0;

  async function handleRun() {
    const numValue = parseFloat(value.replace(/[,$]/g, ""));
    if (!numValue || numValue <= 0) {
      setError("Enter a valid dollar amount");
      return;
    }

    setRunning(true);
    setError(null);

    try {
      const parcel = await ensureBedrockParcel(parcelId);

      // Build a COMPLETE market_context with all required fields,
      // using current values as baseline and overriding only the selected field.
      const marketContext = {
        estimated_home_price: field === "estimated_home_price" ? numValue : baseHomePrice,
        construction_cost_per_home: field === "construction_cost_per_home" ? numValue : baseCostPerHome,
        road_cost_per_ft: baseRoadCost,
        land_price: field === "land_price" ? numValue : baseLandPrice,
      };

      const response = await fetch("/api/bedrock/pipeline/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          parcel,
          market_context: marketContext,
          max_candidates: 12,
        }),
      });

      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        const msg = detail?.detail?.message ?? detail?.detail ?? `Pipeline returned ${response.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }

      const run = await response.json();
      const fr = run.feasibility_result;
      const ia = run.inferred_analysis;

      const scenarioName = `${fieldLabels[field]}: $${numValue.toLocaleString()}`;

      onScenarioCreated({
        name: scenarioName,
        homePrice: fr?.estimated_home_price ?? ia?.price_per_unit ?? marketContext.estimated_home_price,
        costPerHome: fr?.construction_cost_per_home ?? ia?.cost_per_unit ?? marketContext.construction_cost_per_home,
        landBasis: marketContext.land_price,
        units: fr?.units ?? ia?.estimated_units_mid ?? null,
        roi: fr?.ROI_base ?? fr?.ROI ?? ia?.roi ?? null,
        profit: fr?.projected_profit ?? ia?.projected_profit ?? null,
        source: "user_override",
      });

      setValue("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scenario run failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
        What-if calculator
      </div>
      <p className="mt-2 text-xs text-slate-400">
        Override a single assumption and re-run the full pipeline. Result appears as a new scenario row above.
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Variable</span>
          <select
            value={field}
            onChange={(e) => setField(e.target.value as typeof field)}
            className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          >
            <option value="land_price">Land basis</option>
            <option value="estimated_home_price">Home price</option>
            <option value="construction_cost_per_home">Construction cost/home</option>
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Value ($)</span>
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={`e.g. ${Math.round(field === "land_price" ? baseLandPrice || 500000 : field === "estimated_home_price" ? baseHomePrice : baseCostPerHome).toLocaleString()}`}
            className="w-40 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
        </label>

        <button
          onClick={() => void handleRun()}
          disabled={running || !value.trim()}
          className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50"
        >
          {running ? "Running..." : "Run scenario"}
        </button>
      </div>

      <div className="mt-3 text-[10px] text-slate-600">
        Base: price ${baseHomePrice.toLocaleString()} · cost ${baseCostPerHome.toLocaleString()} · land ${baseLandPrice.toLocaleString()} · road ${baseRoadCost.toLocaleString()}/ft
      </div>

      {error ? (
        <div className="mt-3 text-xs text-rose-300">{error}</div>
      ) : null}
    </div>
  );
}
