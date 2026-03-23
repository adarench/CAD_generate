"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { PlanSvgCanvas } from "@/components/studio/PlanSvgCanvas";
import { fetchBedrockParcel, fetchRun } from "@/lib/api";
import { layoutVisualizationFromPipelineRun, studioParcelFromBedrock } from "@/lib/parcels";

interface RunProps {
  params: { runId: string };
}

const layerOptions = ["parcel", "road", "easements", "lots", "lot_labels"] as const;

export default function RunPage({ params }: RunProps) {
  const runQuery = useQuery({
    queryKey: ["run", params.runId],
    queryFn: () => fetchRun(params.runId),
    retry: false,
  });
  const parcelQuery = useQuery({
    queryKey: ["run-parcel", runQuery.data?.parcel_id],
    queryFn: () => fetchBedrockParcel(runQuery.data!.parcel_id),
    enabled: Boolean(runQuery.data?.parcel_id),
    retry: false,
  });
  const [visibleLayers, setVisibleLayers] = useState<(typeof layerOptions)[number][]>([...layerOptions]);

  const run = runQuery.data ?? null;
  const parcel = parcelQuery.data ?? null;
  const studioParcel = parcel ? studioParcelFromBedrock(parcel) : null;
  const visualization = useMemo(
    () => (run ? layoutVisualizationFromPipelineRun(run, parcel) : null),
    [parcel, run]
  );

  return (
    <div className="grid h-[calc(100vh-72px)] overflow-hidden grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)_380px]">
      <aside className="overflow-y-auto border-r border-slate-800 bg-slate-950/75 p-5">
        <Panel title="Saved run">
          <h1 className="text-xl font-semibold text-slate-100">{params.runId}</h1>
          <div className="mt-4 space-y-2 text-sm text-slate-300">
            <p>Parcel ID: {run?.parcel_id ?? "Loading..."}</p>
            <p>Jurisdiction: {parcel?.jurisdiction ?? "—"}</p>
            <p>APN: {studioParcel?.apn ?? "—"}</p>
            <p>Status: {run?.feasibility_result.status ?? "—"}</p>
            <p>Saved: {run ? formatTimestamp(run.timestamp) : "—"}</p>
          </div>
          {run?.parcel_id ? (
            <Link
              href={`/studio/${run.parcel_id}`}
              className="mt-4 inline-flex rounded-2xl border border-cyan-400/40 px-4 py-2 text-sm font-semibold text-cyan-300"
            >
              Open parcel in Studio
            </Link>
          ) : null}
        </Panel>

        <Panel title="Layer controls">
          <div className="grid grid-cols-2 gap-2">
            {layerOptions.map((layer) => {
              const active = visibleLayers.includes(layer);
              return (
                <button
                  key={layer}
                  className={`rounded-2xl border px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] ${
                    active
                      ? "border-emerald-400/50 bg-emerald-400/10 text-emerald-300"
                      : "border-slate-700 text-slate-400"
                  }`}
                  onClick={() =>
                    setVisibleLayers((current) =>
                      current.includes(layer)
                        ? current.filter((item) => item !== layer)
                        : [...current, layer]
                    )
                  }
                >
                  {layer.replace("_", " ")}
                </button>
              );
            })}
          </div>
        </Panel>

        <Panel title="Run metadata">
          <div className="space-y-2 text-sm text-slate-300">
            <p>Git commit: {run?.git_commit ?? "—"}</p>
            <p>Input hash: {run?.input_hash ?? "—"}</p>
          </div>
          {run?.stage_runtimes && Object.keys(run.stage_runtimes).length ? (
            <div className="mt-4 space-y-2 text-sm text-slate-300">
              {Object.entries(run.stage_runtimes).map(([stage, seconds]) => (
                <div key={stage} className="flex items-center justify-between gap-3 rounded-xl bg-slate-950/60 px-3 py-2">
                  <span className="text-slate-500">{stage}</span>
                  <span className="font-mono">{seconds.toFixed(3)}s</span>
                </div>
              ))}
            </div>
          ) : null}
        </Panel>

        <Link
          href="/runs"
          className="mt-4 inline-flex rounded-2xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
        >
          Back to run history
        </Link>
      </aside>

      <section className="min-h-0 border-r border-slate-800 bg-[#dde4e8]">
        <PlanSvgCanvas parcel={studioParcel} result={visualization} visibleLayers={visibleLayers} resetNonce={0} />
      </section>

      <aside className="overflow-y-auto bg-slate-950/85 p-5">
        <Panel title="Feasibility summary">
          {run ? (
            <div className="space-y-2 text-sm text-slate-300">
              <p>Units: {run.feasibility_result.units}</p>
              <p>Projected revenue: {formatCurrency(run.feasibility_result.projected_revenue)}</p>
              <p>Projected cost: {formatCurrency(run.feasibility_result.projected_cost)}</p>
              <p>Projected profit: {formatCurrency(run.feasibility_result.projected_profit)}</p>
              <p>ROI: {formatPercent(run.feasibility_result.ROI)}</p>
              <p>Risk score: {formatNumber(run.feasibility_result.risk_score)}</p>
              <p>Confidence: {formatPercent(run.feasibility_result.confidence)}</p>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Loading run...</p>
          )}
        </Panel>

        <Panel title="Layout summary">
          {visualization ? (
            <div className="space-y-2 text-sm text-slate-300">
              <p>Layout ID: {visualization.layoutId}</p>
              <p>Lot count: {visualization.lotCount}</p>
              <p>Road length: {Math.round(visualization.roadLengthFt).toLocaleString()} ft</p>
              <p>Average lot size: {visualization.averageLotAreaSqft?.toLocaleString() ?? "—"} sqft</p>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Layout geometry unavailable.</p>
          )}
        </Panel>

        <Panel title="Zoning summary">
          {run ? (
            <div className="space-y-2 text-sm text-slate-300">
              <p>District: {run.zoning_result.district}</p>
              <p>Min lot size: {formatSqft(run.zoning_result.min_lot_size_sqft)}</p>
              <p>Max units / acre: {formatNumber(run.zoning_result.max_units_per_acre)}</p>
              <p>Front setback: {formatFeet(run.zoning_result.setbacks.front)}</p>
              <p>Side setback: {formatFeet(run.zoning_result.setbacks.side)}</p>
              <p>Rear setback: {formatFeet(run.zoning_result.setbacks.rear)}</p>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Loading zoning...</p>
          )}
        </Panel>
      </aside>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4 rounded-[24px] border border-slate-800 bg-slate-900/70 p-5 first:mt-0">
      <div className="mb-4 text-xs uppercase tracking-[0.32em] text-slate-500">{title}</div>
      {children}
    </section>
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

function formatNumber(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

function formatFeet(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${value.toFixed(0)} ft`;
}

function formatSqft(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${Math.round(value).toLocaleString()} sqft`;
}

function formatTimestamp(value: string) {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return value;
  return timestamp.toLocaleString();
}
