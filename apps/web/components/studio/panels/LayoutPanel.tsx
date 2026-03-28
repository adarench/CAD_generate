"use client";

import type { BedrockParcel, PipelineRun } from "@/lib/parcels";
import type { LayoutVisualizationResult } from "@/lib/parcels";

import { StatusRow, WorkspaceSection } from "./shared";

export function LayoutPanel({
  parcel,
  resolvedRun,
  visualization,
  activeLayoutId,
  activeLotCount,
  activeRoadLengthFt,
  designModeActive,
  strategyContext,
  exportingDxf,
  onExportDxf,
  onExportGeoJson,
}: {
  parcel: BedrockParcel | null;
  resolvedRun: PipelineRun | null;
  visualization: LayoutVisualizationResult | null;
  activeLayoutId: string | null;
  activeLotCount: number | null;
  activeRoadLengthFt: number | null;
  designModeActive: boolean;
  strategyContext: string | null;
  exportingDxf: boolean;
  onExportDxf: () => void;
  onExportGeoJson: () => void;
}) {
  return (
    <>
      <WorkspaceSection eyebrow="Physical plan" title="Layout and site plan">
        {visualization ? (
          <div className="space-y-3 text-sm text-slate-300">
            <StatusRow label="Source" value={designModeActive ? "design mode" : "pipeline"} />
            <StatusRow label="Layout ID" value={activeLayoutId ?? "—"} mono />
            <StatusRow label="Units" value={activeLotCount !== null ? String(activeLotCount) : "—"} />
            <StatusRow
              label="Road length"
              value={activeRoadLengthFt !== null ? `${Math.round(activeRoadLengthFt).toLocaleString()} ft` : "—"}
            />
            <StatusRow label="Strategy / attempt context" value={strategyContext ?? "Not exposed"} />
            <StatusRow label="Parcel area" value={visualization.parcelAreaSqft ? `${Math.round(visualization.parcelAreaSqft).toLocaleString()} sqft` : "—"} />
            <StatusRow label="Average lot size" value={visualization.averageLotAreaSqft ? `${visualization.averageLotAreaSqft.toLocaleString()} sqft` : "—"} />
          </div>
        ) : resolvedRun ? (
          <p className="text-sm leading-7 text-slate-400">
            No physical plan is currently loaded for this parcel.
          </p>
        ) : (
          <p className="text-sm leading-7 text-slate-400">
            The canvas will render the parcel plan after layout generation or design mode execution.
          </p>
        )}
        {visualization ? (
          <div className="mt-4 grid gap-3">
            <button
              className="w-full rounded-[18px] border border-cyan-400/50 bg-cyan-400/10 px-4 py-3 text-sm font-semibold uppercase tracking-[0.18em] text-cyan-100 transition hover:border-cyan-300 hover:text-cyan-50 disabled:opacity-50"
              onClick={onExportDxf}
              disabled={exportingDxf || !parcel}
            >
              {exportingDxf ? "Exporting DXF..." : "Export DXF"}
            </button>
            <button
              className="w-full rounded-[18px] border border-slate-700 bg-slate-950/70 px-4 py-3 text-sm font-semibold uppercase tracking-[0.18em] text-slate-100 transition hover:border-cyan-400 hover:text-cyan-200"
              onClick={onExportGeoJson}
            >
              Export GeoJSON
            </button>
            <div className="rounded-[18px] border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-xs leading-6 text-amber-100">
              Only DXF and GeoJSON export are available from this Studio flow. DWG and STEP are not exposed here.
            </div>
          </div>
        ) : null}
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
            <StatusRow
              label="Fallback status"
              value={resolvedRun.zoning_bypassed ? `fallback (${resolvedRun.bypass_reason ?? "unspecified"})` : "primary zoning path"}
            />
          </div>
        ) : (
          <p className="text-sm leading-7 text-slate-400">
            Zoning rules are attached automatically when the pipeline succeeds.
          </p>
        )}
      </WorkspaceSection>
    </>
  );
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
