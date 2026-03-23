"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { StudioCanvas, type StudioLayerKey } from "@/components/studio/StudioCanvas";
import { ensureBedrockParcel, fetchRun, fetchRuns, runBedrockPipeline } from "@/lib/api";
import type { BasemapMode } from "@/lib/mapConfig";
import type { BedrockParcel, PipelineRun } from "@/lib/parcels";
import { layoutVisualizationFromPipelineRun, studioParcelFromBedrock } from "@/lib/parcels";

const defaultVisibleLayers: StudioLayerKey[] = ["parcel", "road", "lots", "lot_labels"];

interface StudioWorkspaceProps {
  parcelId: string;
  initialParcel?: BedrockParcel | null;
}

export function StudioWorkspace({ parcelId, initialParcel = null }: StudioWorkspaceProps) {
  const queryClient = useQueryClient();
  const parcelQuery = useQuery({
    queryKey: ["studio-parcel", parcelId],
    queryFn: () => ensureBedrockParcel(parcelId),
    initialData: initialParcel ?? undefined,
    retry: false,
  });
  const runsQuery = useQuery({
    queryKey: ["studio-runs"],
    queryFn: () => fetchRuns({ limit: 24, sort: "timestamp", order: "desc" }),
  });

  const [basemapMode, setBasemapMode] = useState<BasemapMode>("drawing");
  const [visibleLayers, setVisibleLayers] = useState<StudioLayerKey[]>(defaultVisibleLayers);
  const [resetNonce, setResetNonce] = useState(0);
  const [activeRun, setActiveRun] = useState<PipelineRun | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const parcelRuns = useMemo(
    () => (runsQuery.data ?? []).filter((run) => run.parcel_id === parcelId).slice(0, 6),
    [parcelId, runsQuery.data]
  );
  const latestRunQuery = useQuery({
    queryKey: ["studio-run", parcelRuns[0]?.run_id],
    queryFn: () => fetchRun(parcelRuns[0]!.run_id),
    enabled: Boolean(parcelRuns[0]?.run_id) && !activeRun,
    retry: false,
  });

  const parcel = parcelQuery.data ?? null;
  const studioParcel = parcel ? studioParcelFromBedrock(parcel) : null;
  const resolvedRun = activeRun ?? latestRunQuery.data ?? null;
  const visualization = resolvedRun ? layoutVisualizationFromPipelineRun(resolvedRun, parcel) : null;

  async function handleRun() {
    if (!parcel) return;
    setRunning(true);
    setRunError(null);
    try {
      const run = await runBedrockPipeline(parcel);
      setActiveRun(run);
      await queryClient.invalidateQueries({ queryKey: ["studio-runs"] });
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Pipeline execution failed.");
    } finally {
      setRunning(false);
    }
  }

  function toggleLayer(layer: StudioLayerKey) {
    setVisibleLayers((current) =>
      current.includes(layer) ? current.filter((item) => item !== layer) : [...current, layer]
    );
  }

  return (
    <div className="grid h-[calc(100vh-72px)] overflow-hidden grid-cols-1 bg-[#d6dde1] xl:grid-cols-[360px_minmax(0,1fr)_380px]">
      <aside className="border-r border-slate-800/80 bg-slate-950/96 p-5 xl:overflow-y-auto">
        <WorkspaceSection eyebrow="Studio parcel" title={studioParcel?.apn ?? parcelId}>
          <p className="max-w-sm text-sm leading-7 text-slate-300">
            This workspace is now wired to the canonical Bedrock pipeline. Parcel load and feasibility
            execution happen through Bedrock APIs only.
          </p>
          <div className="mt-5 grid grid-cols-2 gap-3">
            <InfoTile label="Jurisdiction" value={parcel?.jurisdiction ?? (parcelQuery.isLoading ? "Loading..." : "—")} />
            <InfoTile label="Parcel ID" value={parcel?.parcel_id ?? parcelId} />
            <InfoTile label="Area" value={formatArea(parcel)} />
            <InfoTile label="Zoning" value={parcel?.zoning_district ?? "Pending zoning lookup"} />
          </div>
          <button
            className="mt-5 w-full rounded-[24px] bg-cyan-400 px-5 py-4 text-sm font-semibold uppercase tracking-[0.24em] text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300 disabled:opacity-50"
            onClick={handleRun}
            disabled={running || parcelQuery.isLoading || !parcel}
          >
            {running ? "Running feasibility..." : resolvedRun ? "Run feasibility again" : "Run feasibility analysis"}
          </button>
          {parcelQuery.isError ? (
            <Alert tone="error">{parcelQuery.error instanceof Error ? parcelQuery.error.message : "Parcel load failed."}</Alert>
          ) : null}
          {runError ? <Alert tone="error">{runError}</Alert> : null}
        </WorkspaceSection>

        <WorkspaceSection eyebrow="Pipeline status" title="Current analysis">
          <div className="space-y-3 text-sm text-slate-300">
            <StatusRow label="Parcel" value={parcel ? "loaded" : parcelQuery.isLoading ? "loading" : "unavailable"} />
            <StatusRow label="Run" value={resolvedRun ? resolvedRun.run_id : running ? "in progress" : "not started"} mono />
            <StatusRow label="Timestamp" value={resolvedRun ? formatTimestamp(resolvedRun.timestamp) : "—"} />
            <StatusRow label="Git commit" value={resolvedRun?.git_commit ?? "—"} mono />
          </div>
          {resolvedRun?.stage_runtimes && Object.keys(resolvedRun.stage_runtimes).length ? (
            <div className="mt-4 rounded-[20px] border border-slate-800 bg-slate-900/80 p-4 text-sm text-slate-300">
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
                Stage runtimes
              </div>
              <div className="mt-3 space-y-2">
                {Object.entries(resolvedRun.stage_runtimes).map(([stage, seconds]) => (
                  <div key={stage} className="flex items-center justify-between gap-3">
                    <span className="text-slate-400">{stage}</span>
                    <span className="font-mono text-slate-100">{seconds.toFixed(3)}s</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </WorkspaceSection>

        <WorkspaceSection eyebrow="Saved runs" title="Parcel history">
          {parcelRuns.length ? (
            <div className="space-y-3">
              {parcelRuns.map((run) => (
                <Link
                  key={run.run_id}
                  href={`/runs/${run.run_id}`}
                  className="block rounded-[20px] border border-slate-800 bg-slate-900/80 px-4 py-4 text-sm text-slate-300 transition hover:border-slate-600"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-slate-100">{run.run_id.slice(0, 8)}</span>
                    <span className="text-xs uppercase tracking-[0.22em] text-cyan-300">
                      {run.units ?? 0} units
                    </span>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-3 text-xs text-slate-500">
                    <span>{formatTimestamp(run.timestamp)}</span>
                    <span>{formatPercent(run.ROI)}</span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <p className="text-sm leading-7 text-slate-400">
              No Bedrock runs saved for this parcel yet. Run the pipeline once to populate this history.
            </p>
          )}
        </WorkspaceSection>
      </aside>

      <section className="min-h-0 border-r border-slate-300/60 bg-[#dde4e8]">
        <StudioCanvas
          parcel={studioParcel}
          result={visualization}
          visibleLayers={visibleLayers}
          basemapMode={basemapMode}
          resetNonce={resetNonce}
          onToggleLayer={toggleLayer}
          onBasemapChange={setBasemapMode}
          onResetView={() => setResetNonce((current) => current + 1)}
        />
      </section>

      <aside className="bg-slate-950/94 p-5 xl:overflow-y-auto">
        <WorkspaceSection eyebrow="Feasibility" title="Return profile">
          {resolvedRun ? (
            <div className="space-y-3">
              <MetricCard label="Projected profit" value={formatCurrency(resolvedRun.feasibility_result.projected_profit)} />
              <MetricCard label="ROI" value={formatPercent(resolvedRun.feasibility_result.ROI)} />
              <MetricCard label="Revenue" value={formatCurrency(resolvedRun.feasibility_result.projected_revenue)} />
              <MetricCard label="Cost" value={formatCurrency(resolvedRun.feasibility_result.projected_cost)} />
              <MetricCard label="Units" value={String(resolvedRun.feasibility_result.units)} />
              <MetricCard label="Risk score" value={formatNumber(resolvedRun.feasibility_result.risk_score)} />
              <MetricCard label="Confidence" value={formatPercent(resolvedRun.feasibility_result.confidence)} />
            </div>
          ) : (
            <p className="text-sm leading-7 text-slate-400">
              Run the pipeline to generate a canonical feasibility report for this parcel.
            </p>
          )}
        </WorkspaceSection>

        <WorkspaceSection eyebrow="Layout" title="Geometry summary">
          {visualization ? (
            <div className="space-y-3 text-sm text-slate-300">
              <StatusRow label="Layout ID" value={visualization.layoutId} mono />
              <StatusRow label="Lot count" value={String(visualization.lotCount)} />
              <StatusRow label="Road length" value={`${Math.round(visualization.roadLengthFt).toLocaleString()} ft`} />
              <StatusRow label="Parcel area" value={visualization.parcelAreaSqft ? `${Math.round(visualization.parcelAreaSqft).toLocaleString()} sqft` : "—"} />
              <StatusRow label="Average lot size" value={visualization.averageLotAreaSqft ? `${visualization.averageLotAreaSqft.toLocaleString()} sqft` : "—"} />
            </div>
          ) : (
            <p className="text-sm leading-7 text-slate-400">
              The drawing canvas will render layout geometry after the pipeline returns a saved run.
            </p>
          )}
        </WorkspaceSection>

        <WorkspaceSection eyebrow="Zoning" title="Applied rules">
          {resolvedRun ? (
            <div className="space-y-3 text-sm text-slate-300">
              <StatusRow label="District" value={resolvedRun.zoning_result.district} />
              <StatusRow label="Min lot size" value={formatSqft(resolvedRun.zoning_result.min_lot_size_sqft)} />
              <StatusRow label="Max units / acre" value={formatNumber(resolvedRun.zoning_result.max_units_per_acre)} />
              <StatusRow label="Front setback" value={formatFeet(resolvedRun.zoning_result.setbacks.front)} />
              <StatusRow label="Side setback" value={formatFeet(resolvedRun.zoning_result.setbacks.side)} />
              <StatusRow label="Rear setback" value={formatFeet(resolvedRun.zoning_result.setbacks.rear)} />
            </div>
          ) : (
            <p className="text-sm leading-7 text-slate-400">
              Zoning rules are attached automatically when the pipeline succeeds.
            </p>
          )}
        </WorkspaceSection>
      </aside>
    </div>
  );
}

function WorkspaceSection({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-4 rounded-[28px] border border-slate-800 bg-slate-900/70 p-5 first:mt-0">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">{eyebrow}</div>
      <h2 className="mt-2 text-xl font-semibold text-slate-100">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-4">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-2 text-sm text-slate-200">{value}</div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[20px] border border-slate-800 bg-slate-900/80 px-4 py-4">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-2 text-lg font-semibold text-slate-100">{value}</div>
    </div>
  );
}

function StatusRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-[18px] border border-slate-800 bg-slate-950/70 px-4 py-3">
      <span className="text-slate-500">{label}</span>
      <span className={mono ? "font-mono text-slate-100" : "text-slate-100"}>{value}</span>
    </div>
  );
}

function Alert({ tone, children }: { tone: "error"; children: React.ReactNode }) {
  const classes =
    tone === "error"
      ? "border-red-500/30 bg-red-500/10 text-red-200"
      : "border-slate-700 bg-slate-900/80 text-slate-200";
  return <div className={`mt-4 rounded-[20px] border px-4 py-3 text-sm ${classes}`}>{children}</div>;
}

function formatArea(parcel: BedrockParcel | null) {
  if (!parcel) return "—";
  const acres = parcel.area_sqft / 43560;
  return `${acres.toFixed(2)} ac`;
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
