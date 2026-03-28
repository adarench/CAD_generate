"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { PlanSvgCanvas } from "@/components/studio/PlanSvgCanvas";
import { fetchBedrockParcel, fetchRun, fetchRuns } from "@/lib/api";
import { buildParcelMemory } from "@/lib/runMemory";
import {
  layoutVisualizationFromPipelineRun,
  pipelineRunExplanation,
  pipelineRunStateLabel,
  pipelineRunUiState,
  studioParcelFromBedrock,
} from "@/lib/parcels";

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
  const parcelMemoryQuery = useQuery({
    queryKey: ["run-memory", runQuery.data?.parcel_id],
    queryFn: async () => {
      const summaries = await fetchRuns({ limit: 48, sort: "timestamp", order: "desc" });
      const matching = summaries.filter((summary) => summary.parcel_id === runQuery.data?.parcel_id);
      return Promise.all(matching.map((summary) => fetchRun(summary.run_id)));
    },
    enabled: Boolean(runQuery.data?.parcel_id),
    retry: false,
  });
  const [visibleLayers, setVisibleLayers] = useState<(typeof layerOptions)[number][]>([...layerOptions]);

  const run = runQuery.data ?? null;
  const parcel = parcelQuery.data ?? null;
  const parcelMemory = useMemo(() => buildParcelMemory(parcelMemoryQuery.data ?? []), [parcelMemoryQuery.data]);
  const studioParcel = parcel ? studioParcelFromBedrock(parcel) : null;
  const runState = pipelineRunUiState(run);
  const explanation = pipelineRunExplanation(run);
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
            <p>Status: {pipelineRunStateLabel(run)}</p>
            <p>Saved: {run ? formatTimestamp(run.timestamp) : "—"}</p>
          </div>
          {run ? <div className="mt-4"><RunStateBadge status={run.status} /></div> : null}
          {run?.parcel_id ? (
            <Link
              href={`/studio/${run.parcel_id}`}
              className="mt-4 inline-flex rounded-2xl border border-cyan-400/40 px-4 py-2 text-sm font-semibold text-cyan-300"
            >
              Open parcel decision view
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

        <Panel title="Parcel memory">
          {parcelMemory ? (
            <div className="space-y-3 text-sm text-slate-300">
              <p>
                Latest recommendation:{" "}
                <span className="font-semibold text-slate-100">{parcelMemory.latest.decision_label}</span>
              </p>
              <p>
                Previous recommendation:{" "}
                <span className="font-semibold text-slate-100">
                  {parcelMemory.previous?.decision_label ?? "No prior recommendation"}
                </span>
              </p>
              <p>Last updated: {formatTimestamp(parcelMemory.lastUpdatedAt)}</p>
              <p>Saved runs: {parcelMemory.runCount}</p>
              <p>{parcelMemory.changes.summary ?? "No change summary available."}</p>
              <div className="flex flex-wrap gap-2 pt-1">
                {parcelMemory.statusHistory.map((status, index) => (
                  <RunStateBadge key={`${status}-${index}`} status={status} />
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">No parcel history available yet.</p>
          )}
        </Panel>

        <Link
          href="/runs"
          className="mt-4 inline-flex rounded-2xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
        >
          Back to parcel memory
        </Link>
      </aside>

      <section className="min-h-0 border-r border-slate-800 bg-[#dde4e8]">
        <PlanSvgCanvas parcel={studioParcel} result={visualization} visibleLayers={visibleLayers} resetNonce={0} />
      </section>

      <aside className="overflow-y-auto bg-slate-950/85 p-5">
        <Panel title="Decision summary">
          {run ? (
            <div className="space-y-3 text-sm text-slate-300">
              <p>{explanation}</p>
              <p>District: {run.zoning_result.district}</p>
              {run.near_feasible_result?.reason_category ? (
                <p>Reason: {run.near_feasible_result.reason_category.replace(/_/g, " ")}</p>
              ) : run.bypass_reason ? (
                <p>Reason: {run.bypass_reason.replace(/_/g, " ")}</p>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-slate-500">Loading run...</p>
          )}
        </Panel>

        <Panel title="Feasibility summary">
          {run?.feasibility_result ? (
            <div className="space-y-2 text-sm text-slate-300">
              <p>Units: {run.feasibility_result.units}</p>
              <p>Projected revenue: {formatCurrency(run.feasibility_result.projected_revenue)}</p>
              <p>Projected cost: {formatCurrency(run.feasibility_result.projected_cost)}</p>
              <p>Projected profit: {formatCurrency(run.feasibility_result.projected_profit)}</p>
              <p>ROI: {formatPercent(run.feasibility_result.ROI)}</p>
              <p>ROI base: {formatPercent(run.feasibility_result.ROI_base)}</p>
              <p>ROI best case: {formatPercent(run.feasibility_result.ROI_best_case)}</p>
              <p>ROI worst case: {formatPercent(run.feasibility_result.ROI_worst_case)}</p>
              <p>Estimated home price: {formatCurrency(run.feasibility_result.estimated_home_price)}</p>
              <p>Price / sqft: {formatCurrency(run.feasibility_result.price_per_sqft)}</p>
              <p>Construction / sqft: {formatCurrency(run.feasibility_result.construction_cost_per_sqft)}</p>
              <p>Break-even price: {formatCurrency(run.feasibility_result.break_even_price)}</p>
              <p>Risk score: {formatNumber(run.feasibility_result.risk_score)}</p>
              <p>Confidence: {formatPercent(run.feasibility_result.confidence_score ?? run.feasibility_result.confidence)}</p>
            </div>
          ) : run ? (
            <p className="text-sm text-slate-500">
              Feasibility metrics are only available for completed parcels.
            </p>
          ) : (
            <p className="text-sm text-slate-500">Loading run...</p>
          )}
        </Panel>

        <Panel title="Layout summary">
          {visualization && runState === "buildable" ? (
            <div className="space-y-2 text-sm text-slate-300">
              <p>Layout ID: {visualization.layoutId}</p>
              <p>Lot count: {visualization.lotCount}</p>
              <p>Road length: {Math.round(visualization.roadLengthFt).toLocaleString()} ft</p>
              <p>Average lot size: {visualization.averageLotAreaSqft?.toLocaleString() ?? "—"} sqft</p>
            </div>
          ) : run ? (
            <p className="text-sm text-slate-500">
              Layout geometry is only available for buildable parcels.
            </p>
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

        {run?.near_feasible_result ? (
          <Panel title="Near-feasible detail">
            <div className="space-y-3 text-sm text-slate-300">
              <p>Reason category: {run.near_feasible_result.reason_category}</p>
              <p>Attempted strategies: {run.near_feasible_result.attempted_strategies.join(", ") || "—"}</p>
              <pre className="overflow-x-auto rounded-xl bg-slate-950/60 px-3 py-3 text-[11px] leading-5 text-slate-200">
{JSON.stringify(run.near_feasible_result.limiting_constraints, null, 2)}
              </pre>
              <pre className="overflow-x-auto rounded-xl bg-slate-950/60 px-3 py-3 text-[11px] leading-5 text-slate-200">
{JSON.stringify(run.near_feasible_result.required_relaxation, null, 2)}
              </pre>
              <pre className="overflow-x-auto rounded-xl bg-slate-950/60 px-3 py-3 text-[11px] leading-5 text-slate-200">
{JSON.stringify(run.near_feasible_result.best_attempt_summary, null, 2)}
              </pre>
            </div>
          </Panel>
        ) : null}
      </aside>
    </div>
  );
}

function RunStateBadge({ status }: { status: "completed" | "near_feasible" | "failed" }) {
  const tone =
    status === "completed"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
      : status === "near_feasible"
        ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
        : "border-rose-400/40 bg-rose-400/10 text-rose-300";
  const label = status === "completed" ? "Buildable" : status === "near_feasible" ? "Near-feasible" : "Failed";
  return <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${tone}`}>{label}</span>;
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
