"use client";

import type { BedrockParcel } from "@/lib/parcels";

import { Alert, InfoTile, WorkspaceSection } from "./shared";

export function ParcelHeader({
  title,
  parcel,
  parcelId,
  parcelLoading,
  runLoading,
  designLoading,
  parcelError,
  runError,
  designError,
  exportError,
  onRun,
  onDesign,
  formatArea,
}: {
  title: string;
  parcel: BedrockParcel | null;
  parcelId: string;
  parcelLoading: boolean;
  runLoading: boolean;
  designLoading: boolean;
  parcelError?: string | null;
  runError?: string | null;
  designError?: string | null;
  exportError?: string | null;
  onRun: () => void;
  onDesign: () => void;
  formatArea: (parcel: BedrockParcel | null) => string;
}) {
  return (
    <WorkspaceSection eyebrow="Parcel decision view" title={title}>
      <p className="max-w-sm text-sm leading-7 text-slate-300">
        This parcel decision view is wired to the canonical Bedrock pipeline. Parcel load, layout,
        and feasibility execution happen through Bedrock APIs only.
      </p>
      <div className="mt-5 grid grid-cols-2 gap-3">
        <InfoTile label="Jurisdiction" value={parcel?.jurisdiction ?? (parcelLoading ? "Loading..." : "—")} />
        <InfoTile label="Parcel ID" value={parcel?.parcel_id ?? parcelId} />
        <InfoTile label="Area" value={formatArea(parcel)} />
        <InfoTile label="Zoning" value={parcel?.zoning_district ?? "Pending zoning lookup"} />
      </div>
      <button
        className="mt-5 w-full rounded-[24px] bg-cyan-400 px-5 py-4 text-sm font-semibold uppercase tracking-[0.24em] text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300 disabled:opacity-50"
        onClick={onRun}
        disabled={runLoading || parcelLoading || !parcel}
      >
        {runLoading ? "Running feasibility..." : "Run Feasibility"}
      </button>
      <button
        className="mt-3 w-full rounded-[24px] border border-cyan-400/40 bg-transparent px-5 py-4 text-sm font-semibold uppercase tracking-[0.24em] text-cyan-200 transition hover:border-cyan-300 hover:text-cyan-100 disabled:opacity-50"
        onClick={onDesign}
        disabled={designLoading || parcelLoading || !parcel}
      >
        {designLoading ? "Regenerating layout..." : "Design Layout"}
      </button>
      {parcelError ? <Alert tone="error">{parcelError}</Alert> : null}
      {runError ? <Alert tone="error">{runError}</Alert> : null}
      {designError ? <Alert tone="error">{designError}</Alert> : null}
      {exportError ? <Alert tone="error">{exportError}</Alert> : null}
    </WorkspaceSection>
  );
}
