"use client";

import type { BedrockParcel, PipelineRun } from "@/lib/parcels";

import { StatusRow, WorkspaceSection } from "./shared";

export function ProvenancePanel({
  parcel,
  resolvedRun,
}: {
  parcel: BedrockParcel | null;
  resolvedRun: PipelineRun | null;
}) {
  const marketSources = extractMarketSources(resolvedRun);
  const zoningSource = buildZoningSource(resolvedRun);
  const parcelSource = buildParcelSource(parcel);
  const costSource = buildCostSource(resolvedRun);

  return (
    <WorkspaceSection eyebrow="Provenance" title="Where this answer came from">
      <div className="space-y-3 text-sm text-slate-300">
        <StatusRow label="Parcel source" value={parcelSource} />
        <StatusRow label="Zoning source" value={zoningSource} />
        <StatusRow label="Market reference source" value={marketSources.length ? `${marketSources.length} linked sources` : "Not exposed"} />
        <StatusRow label="Cost reference source" value={costSource} />
        <StatusRow label="Run ID" value={resolvedRun?.run_id ?? "Not run yet"} mono />
        <StatusRow label="Run timestamp" value={resolvedRun ? formatTimestamp(resolvedRun.timestamp) : "Not run yet"} />
      </div>
      {marketSources.length ? (
        <div className="mt-4 rounded-[20px] border border-slate-800 bg-slate-900/80 p-4 text-sm text-slate-300">
          <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
            Market sources
          </div>
          <div className="mt-3 space-y-2">
            {marketSources.map(([key, value]) => (
              <div key={key} className="rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3">
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{humanizeKey(key)}</div>
                <div className="mt-2 break-all text-sm text-slate-200">{value}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </WorkspaceSection>
  );
}

function extractMarketSources(run: PipelineRun | null): Array<[string, string]> {
  const sources = run?.feasibility_result?.assumptions?.market_sources;
  if (!sources || typeof sources !== "object") return [];
  return Object.entries(sources as Record<string, unknown>).filter(
    (entry): entry is [string, string] => typeof entry[1] === "string"
  );
}

function buildZoningSource(run: PipelineRun | null) {
  if (!run) return "Not run yet";
  if (run.zoning_bypassed) {
    return `Fallback zoning${run.bypass_reason ? ` (${run.bypass_reason.replace(/_/g, " ")})` : ""}`;
  }
  if (run.zoning_result.citations?.length) {
    return `Cited zoning rules (${run.zoning_result.citations.length} citations)`;
  }
  return "Zoning attached, but source citations are not exposed";
}

function buildParcelSource(parcel: BedrockParcel | null) {
  const metadata = parcel?.metadata;
  if (metadata && typeof metadata === "object") {
    const sourceProvider = typeof metadata.sourceProvider === "string" ? metadata.sourceProvider : null;
    const sourceDataset = typeof metadata.sourceDataset === "string" ? metadata.sourceDataset : null;
    const pieces = [sourceProvider, sourceDataset].filter(Boolean);
    if (pieces.length) return pieces.join(" • ");
  }
  return "Canonical Bedrock parcel record";
}

function buildCostSource(run: PipelineRun | null) {
  const marketContext = run?.feasibility_result?.financial_summary?.market_context;
  if (marketContext && typeof marketContext === "object") {
    const proxy = (marketContext as Record<string, unknown>).cost_proxy;
    if (typeof proxy === "string") {
      return proxy.replace(/_/g, " ");
    }
  }
  return "Cost reference proxy not exposed";
}

function humanizeKey(key: string) {
  return key.replace(/_/g, " ").trim();
}

function formatTimestamp(value: string) {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return value;
  return timestamp.toLocaleString();
}
