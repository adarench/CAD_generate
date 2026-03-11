"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";

import { fetchParcel, fetchRecentRuns, fetchRun } from "@/lib/api";
import { CONCEPT_PRESET_CHIPS, summarizeAppliedInstruction } from "@/lib/concepts";
import type { BasemapMode } from "@/lib/mapConfig";
import { DEFAULT_STUDIO_DEMO_PARCEL_ID } from "@/lib/mapConfig";
import { runOptimizationApi, type PlannerConstraintOverrides } from "@/lib/optimize";
import type { OptimizationResponse, ParcelRecord, RunDetail, RunSummary } from "@/lib/parcels";
import { StudioCanvas, STUDIO_LAYER_OPTIONS, type StudioLayerKey } from "@/components/studio/StudioCanvas";

const topologyOptions = ["parallel", "spine", "loop", "culdesac"] as const;
const defaultPrompt =
  "Design a subdivision with a central loop road, two cul-de-sac branches, and maximize frontage-compliant lots.";
type StudioConstraints = {
  minFrontage: number;
  minDepth: number;
  minArea: number;
  roadWidth: number;
  easementWidth: number;
  lotCount: number;
  roadOrientation: "north_south" | "east_west";
};

const defaultConstraints: StudioConstraints = {
  minFrontage: 60,
  minDepth: 110,
  minArea: 6000,
  roadWidth: 40,
  easementWidth: 12,
  lotCount: 32,
  roadOrientation: "north_south" as const,
};
const defaultVisibleLayers: StudioLayerKey[] = ["parcel", "road", "lots", "easements", "lot_labels"];

interface StudioWorkspaceProps {
  parcelId: string;
  initialParcel?: ParcelRecord | null;
  initialRun?: RunDetail | null;
}

export function StudioWorkspace({ parcelId, initialParcel = null, initialRun = null }: StudioWorkspaceProps) {
  const parcelQuery = useQuery({
    queryKey: ["studio-parcel", parcelId],
    queryFn: () => fetchParcel(parcelId),
    initialData: initialParcel ?? undefined,
  });
  const recentRunsQuery = useQuery({
    queryKey: ["studio-runs", parcelId],
    queryFn: () => fetchRecentRuns(24),
  });

  const [conceptText, setConceptText] = useState(defaultPrompt);
  const [constraints, setConstraints] = useState<StudioConstraints>(defaultConstraints);
  const [selectedTopologies, setSelectedTopologies] = useState<string[]>(["loop", "culdesac", "spine"]);
  const [strictTopology, setStrictTopology] = useState(false);
  const [showParameters, setShowParameters] = useState(true);
  const [visibleLayers, setVisibleLayers] = useState<StudioLayerKey[]>(defaultVisibleLayers);
  const [basemapMode, setBasemapMode] = useState<BasemapMode>("drawing");
  const [resetNonce, setResetNonce] = useState(0);
  const [results, setResults] = useState<OptimizationResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parcel = parcelQuery.data;
  const parcelRuns = useMemo(
    () => (recentRunsQuery.data ?? []).filter((run) => run.parcelId === parcelId).slice(0, 6),
    [parcelId, recentRunsQuery.data]
  );
  const latestRunQuery = useQuery({
    queryKey: ["studio-latest-run", parcelRuns[0]?.runId],
    queryFn: () => fetchRun(parcelRuns[0]!.runId),
    enabled: Boolean(parcelRuns[0]?.runId) && !results,
    initialData: initialRun ?? undefined,
  });
  const activeRun = results ? null : latestRunQuery.data ?? null;
  const activeResults = results ?? activeRun?.response ?? null;
  const activeRunId = results?.runId ?? activeRun?.runId ?? null;
  const conceptSummary =
    activeResults?.conceptSummary ??
    summarizeAppliedInstruction(activeResults?.appliedInstruction) ??
    "Prompt-first concept planning for this parcel.";
  const workflowNotes = useMemo(
    () => buildWorkflowNotes(activeResults, strictTopology, conceptSummary),
    [activeResults, strictTopology, conceptSummary]
  );
  const resultExports = useMemo(
    () => Object.entries(activeResults?.exports ?? {}).filter(([, value]) => Boolean(value)),
    [activeResults]
  );
  const parcelAreaSqft = parcel?.areaSqft ?? null;
  const parcelAppearsTooSmall = Boolean(parcelAreaSqft && parcelAreaSqft < constraints.minArea * 2);
  const zeroLotRun = Boolean(activeResults && activeResults.lotCount === 0);
  const lotsRendered = Boolean(
    activeResults?.resultGeoJSON?.features.some((feature) => feature.properties?.layer === "lots")
  );
  const lotlessRun = Boolean(activeResults && !lotsRendered);

  async function handleRun() {
    if (!parcel) return;
    setRunning(true);
    setError(null);
    try {
      const parameterOverrides = diffConstraintOverrides(constraints);
      const response = await runOptimizationApi(
        parcel,
        parameterOverrides,
        selectedTopologies.length ? selectedTopologies : ["all"],
        strictTopology,
        conceptText
      );
      setResults(response);
      void recentRunsQuery.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Concept generation failed.");
    } finally {
      setRunning(false);
    }
  }

  function handleResetWorkspace() {
    setConceptText(defaultPrompt);
    setConstraints(defaultConstraints);
    setSelectedTopologies(["loop", "culdesac", "spine"]);
    setStrictTopology(false);
    setBasemapMode("drawing");
    setVisibleLayers(defaultVisibleLayers);
    setResults(null);
    setError(null);
    setResetNonce((current) => current + 1);
  }

  function toggleLayer(layer: StudioLayerKey) {
    setVisibleLayers((current) =>
      current.includes(layer) ? current.filter((item) => item !== layer) : [...current, layer]
    );
  }

  function toggleTopology(topology: string) {
    setSelectedTopologies((current) =>
      current.includes(topology) ? current.filter((item) => item !== topology) : [...current, topology]
    );
  }

  const parcelLabel = parcel?.apn ?? parcelId;

  return (
    <div className="grid h-[calc(100vh-72px)] overflow-hidden grid-cols-1 bg-[#d6dde1] xl:grid-cols-[360px_minmax(0,1fr)_400px]">
      <aside className="border-r border-slate-800/80 bg-slate-950/96 p-5 xl:overflow-y-auto">
        <WorkspaceSection eyebrow="Studio parcel" title={parcelLabel}>
          <p className="max-w-sm text-sm leading-7 text-slate-300">
            Selected from the Discovery layer. This workspace is parcel-locked and focused on concept
            generation, not browsing geography.
          </p>
          {parcelAppearsTooSmall ? (
            <div className="mt-4 rounded-[22px] border border-amber-400/30 bg-amber-400/10 px-4 py-4 text-sm leading-7 text-amber-100">
              This parcel is likely too small for a meaningful subdivision under the current zoning
              assumptions. You can still test prompts here, but expect a constrained or zero-lot result.
            </div>
          ) : null}
          <div className="mt-5 grid grid-cols-2 gap-3">
            <InfoTile label="County" value={parcel?.county ?? "Loading..."} />
            <InfoTile label="APN" value={parcel?.apn ?? "—"} />
            <InfoTile label="Area" value={formatArea(parcel)} />
            <InfoTile label="Zoning" value={parcel?.zoningCode ?? "Enrichment pending"} />
            <InfoTile label="Dataset" value={parcel?.sourceDataset ?? "—"} />
            <InfoTile label="Object ID" value={parcel?.sourceObjectId ?? "—"} />
          </div>
        </WorkspaceSection>

        <WorkspaceSection eyebrow="Primary input" title="Describe the concept plan">
          <label className="text-sm leading-7 text-slate-400">
            The prompt is the main control surface. Use it to describe street structure, density, lot
            character, and topology intent.
          </label>
          <textarea
            className="mt-4 h-48 w-full rounded-[28px] border border-slate-800 bg-slate-900/80 px-5 py-5 text-base leading-8 text-slate-100 outline-none transition focus:border-cyan-400/60"
            value={conceptText}
            onChange={(event) => setConceptText(event.target.value)}
            placeholder="Create a subdivision with a central loop road, two cul-de-sac branches, and maximize frontage-compliant lots."
          />
          <div className="mt-4 flex flex-wrap gap-2">
            {CONCEPT_PRESET_CHIPS.map((chip) => (
              <button
                key={chip.label}
                className="rounded-full border border-slate-700 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300 transition hover:border-slate-500"
                onClick={() => setConceptText(chip.instruction)}
              >
                {chip.label}
              </button>
            ))}
          </div>
          <button
            className="mt-5 w-full rounded-[24px] bg-cyan-400 px-5 py-4 text-sm font-semibold uppercase tracking-[0.24em] text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300 disabled:opacity-50"
            onClick={handleRun}
            disabled={running || !parcel}
          >
            {running ? "Generating concept..." : results ? "Refine concept plan" : "Generate concept plan"}
          </button>
          {error ? (
            <div className="mt-4 rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          ) : null}
        </WorkspaceSection>

        <WorkspaceSection eyebrow="Secondary controls" title="Parameter panel">
          <div className="flex items-center justify-between gap-3 rounded-[22px] border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-300">
            <span>Optional structured controls</span>
            <button
              className="rounded-full border border-slate-700 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-300"
              onClick={() => setShowParameters((current) => !current)}
            >
              {showParameters ? "Collapse" : "Expand"}
            </button>
          </div>
          {showParameters ? (
            <div className="mt-4 space-y-5">
              <div className="grid grid-cols-2 gap-3">
                <NumberField
                  label="Min frontage"
                  value={constraints.minFrontage}
                  onChange={(value) => setConstraints({ ...constraints, minFrontage: value })}
                />
                <NumberField
                  label="Min depth"
                  value={constraints.minDepth}
                  onChange={(value) => setConstraints({ ...constraints, minDepth: value })}
                />
                <NumberField
                  label="Min area"
                  value={constraints.minArea}
                  onChange={(value) => setConstraints({ ...constraints, minArea: value })}
                />
                <NumberField
                  label="Target lots"
                  value={constraints.lotCount}
                  onChange={(value) => setConstraints({ ...constraints, lotCount: value })}
                />
                <NumberField
                  label="Road width"
                  value={constraints.roadWidth}
                  onChange={(value) => setConstraints({ ...constraints, roadWidth: value })}
                />
                <NumberField
                  label="Easement width"
                  value={constraints.easementWidth}
                  onChange={(value) => setConstraints({ ...constraints, easementWidth: value })}
                />
              </div>

              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
                  Topology preferences
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {topologyOptions.map((option) => {
                    const active = selectedTopologies.includes(option);
                    return (
                      <button
                        key={option}
                        className={`rounded-full px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] transition ${
                          active
                            ? "bg-emerald-400 text-slate-950"
                            : "border border-slate-700 text-slate-300 hover:border-slate-500"
                        }`}
                        onClick={() => toggleTopology(option)}
                      >
                        {option}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <label className="rounded-[22px] border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-300">
                  <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Road orientation</div>
                  <select
                    className="mt-2 w-full bg-transparent text-sm text-slate-100 outline-none"
                    value={constraints.roadOrientation}
                    onChange={(event) =>
                      setConstraints({
                        ...constraints,
                        roadOrientation: event.target.value as "north_south" | "east_west",
                      })
                    }
                  >
                    <option value="north_south">North-south</option>
                    <option value="east_west">East-west</option>
                  </select>
                </label>
                <label className="flex items-center gap-3 rounded-[22px] border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={strictTopology}
                    onChange={(event) => setStrictTopology(event.target.checked)}
                  />
                  <span>Strict topology mode</span>
                </label>
              </div>
            </div>
          ) : null}
        </WorkspaceSection>

        <WorkspaceSection eyebrow="Actions" title="Workspace controls">
          <div className="grid gap-3">
            <ActionButton onClick={handleRun} disabled={running || !parcel} tone="secondary">
              {activeResults ? "Re-run optimization" : "Generate concept plan"}
            </ActionButton>
            <ActionButton
              onClick={() => activeRunId && window.open(`/runs/${activeRunId}`, "_blank", "noopener,noreferrer")}
              disabled={!activeRunId}
              tone="secondary"
            >
              Save run
            </ActionButton>
            <ActionButton onClick={handleResetWorkspace} tone="ghost">
              Reset workspace
            </ActionButton>
          </div>
          <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-400">
            Every generation is persisted automatically. The save action opens the latest stored run
            artifact set.
          </div>
        </WorkspaceSection>
      </aside>

      <section className="flex min-h-0 flex-col border-r border-slate-800/60 bg-[#dde4e8]">
        <div className="border-b border-slate-800/60 bg-slate-950/92 px-6 py-5 text-slate-50">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.32em] text-cyan-300">
                Studio design / feasibility layer
              </div>
              <h1 className="mt-2 text-3xl font-semibold">Parcel concept workspace</h1>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300">{conceptSummary}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusPill label={parcel ? `${parcel.county} County` : "Loading parcel"} />
              <StatusPill label={activeResults ? `${activeResults.winningTopology} winner` : "Awaiting run"} />
              <StatusPill label={strictTopology ? "Strict topology" : "Flexible topology"} />
              <StatusPill label={`${visibleLayers.length}/${STUDIO_LAYER_OPTIONS.length} layers`} />
            </div>
          </div>
        </div>

        {zeroLotRun || lotlessRun ? (
          <div className="border-b border-amber-500/30 bg-amber-500/10 px-6 py-4 text-sm text-amber-100">
            <div className="font-semibold uppercase tracking-[0.22em] text-amber-200">Constrained parcel</div>
            <p className="mt-2 max-w-4xl leading-7">
              The optimizer did not generate buildable lots for this parcel under the current rules. The
              canvas is showing the real parcel, road, and easement geometry from the run, but this is not
              a viable subdivision layout. Try looser constraints or open the larger demo parcel for a
              full lot-yield example.
            </p>
            <div className="mt-3">
              <Link
                href={`/studio/${DEFAULT_STUDIO_DEMO_PARCEL_ID}`}
                className="inline-flex rounded-full border border-amber-300/50 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-amber-100 transition hover:border-amber-200"
              >
                Open large demo parcel
              </Link>
            </div>
          </div>
        ) : null}

        <StudioCanvas
          parcel={parcel}
          result={activeResults}
          visibleLayers={visibleLayers}
          basemapMode={basemapMode}
          resetNonce={resetNonce}
          onToggleLayer={toggleLayer}
          onBasemapChange={setBasemapMode}
          onResetView={() => setResetNonce((current) => current + 1)}
        />
      </section>

      <aside className="bg-[#eff3f5] p-5 xl:overflow-y-auto">
        <AnalysisSection eyebrow="Feasibility summary" title="Current plan intelligence">
          <div className="grid grid-cols-2 gap-3">
            <SummaryCard label="Winning topology" value={activeResults?.winningTopology ?? "Awaiting run"} />
            <SummaryCard label="Lot yield" value={activeResults ? `${activeResults.lotCount}` : "—"} />
            <SummaryCard label="Parcel area" value={formatArea(parcel)} />
            <SummaryCard
              label="Developable area"
              value={activeResults?.developableAreaSqft ? `${Math.round(activeResults.developableAreaSqft).toLocaleString()} sqft` : "—"}
            />
            <SummaryCard
              label="Road length"
              value={activeResults?.roadLengthFt ? `${Math.round(activeResults.roadLengthFt).toLocaleString()} ft` : "—"}
            />
            <SummaryCard
              label="Average lot"
              value={activeResults?.averageLotAreaSqft ? `${Math.round(activeResults.averageLotAreaSqft).toLocaleString()} sqft` : "—"}
            />
          </div>
        </AnalysisSection>

        <AnalysisSection eyebrow="Candidate breakdown" title="Topology comparison">
          <CandidateBreakdownTable results={activeResults} />
        </AnalysisSection>

        <AnalysisSection eyebrow="Workflow notes" title="Prompt interpretation and run notes">
          <div className="space-y-3">
            {workflowNotes.length ? (
              workflowNotes.map((note) => (
                <div
                  key={note}
                  className="rounded-[22px] border border-slate-300 bg-white/90 px-4 py-3 text-sm leading-7 text-slate-700"
                >
                  {note}
                </div>
              ))
            ) : (
              <EmptyMessage>
                Run a concept plan to see prompt interpretation, fallback notes, and topology guidance.
              </EmptyMessage>
            )}
          </div>
        </AnalysisSection>

        <AnalysisSection eyebrow="Exports" title="Geometry outputs">
          <div className="space-y-3">
            {resultExports.length ? (
              resultExports.map(([label, url]) => (
                <a
                  key={label}
                  href={String(url)}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between rounded-[22px] border border-slate-300 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-slate-500"
                >
                  <span>Export {label.toUpperCase()}</span>
                  <span className="text-[11px] font-semibold uppercase tracking-[0.24em] text-cyan-700">
                    Ready
                  </span>
                </a>
              ))
            ) : (
              <EmptyMessage>Generate a concept plan to unlock DXF, STEP, and GeoJSON exports.</EmptyMessage>
            )}
          </div>
        </AnalysisSection>

        <AnalysisSection eyebrow="Saved versions" title="Parcel run history">
          <div className="space-y-3">
            {parcelRuns.length ? (
              parcelRuns.map((run) => <SavedRunCard key={run.runId} run={run} />)
            ) : (
              <EmptyMessage>No saved parcel runs yet. The first concept generation will populate this list.</EmptyMessage>
            )}
          </div>
        </AnalysisSection>
      </aside>
    </div>
  );
}

function buildWorkflowNotes(
  results: OptimizationResponse | null,
  strictTopology: boolean,
  conceptSummary: string
) {
  const notes = [conceptSummary];
  if (results && results.lotCount === 0) {
    notes.push(
      "This run produced no compliant lots. The visible geometry is still the real engine output, but it indicates the parcel is too constrained for subdivision under the current assumptions."
    );
  }
  if (strictTopology) {
    notes.push("Strict topology mode is enabled for this workspace run.");
  }
  if (results?.appliedInstruction) {
    const parsed = summarizeAppliedInstruction(results.appliedInstruction);
    if (parsed) {
      notes.push(`Prompt parser interpretation: ${parsed}`);
    }
  }
  for (const candidate of results?.candidateSummary ?? []) {
    if (candidate.notes) {
      notes.push(`${candidate.topology}: ${candidate.notes}`);
    }
  }
  return Array.from(new Set(notes.filter(Boolean)));
}

function formatArea(parcel: ParcelRecord | null | undefined) {
  if (!parcel) return "—";
  const acres = parcel.areaAcres ? `${parcel.areaAcres.toFixed(2)} ac` : null;
  const sqft = parcel.areaSqft ? `${Math.round(parcel.areaSqft).toLocaleString()} sqft` : null;
  return [acres, sqft].filter(Boolean).join(" • ") || "—";
}

function diffConstraintOverrides(constraints: StudioConstraints): PlannerConstraintOverrides {
  return Object.fromEntries(
    Object.entries(constraints).filter(([key, value]) => defaultConstraints[key as keyof StudioConstraints] !== value)
  ) as PlannerConstraintOverrides;
}

function WorkspaceSection({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="mt-4 rounded-[30px] border border-slate-800 bg-slate-950/80 p-5 first:mt-0">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">{eyebrow}</div>
      <h2 className="mt-2 text-xl font-semibold text-slate-100">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function AnalysisSection({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="mt-4 rounded-[30px] border border-slate-300/80 bg-white/75 p-5 shadow-sm shadow-slate-400/10 first:mt-0">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">{eyebrow}</div>
      <h2 className="mt-2 text-xl font-semibold text-slate-900">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-slate-800 bg-slate-900/70 px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-2 text-sm text-slate-200">{value}</div>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-slate-300 bg-white px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-2 text-sm font-semibold text-slate-900">{value}</div>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="rounded-[22px] border border-slate-800 bg-slate-900/70 px-4 py-3">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <input
        className="mt-2 w-full bg-transparent text-sm text-slate-100 outline-none"
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function ActionButton({
  children,
  disabled,
  onClick,
  tone,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  tone: "secondary" | "ghost";
}) {
  return (
    <button
      className={`rounded-[22px] px-4 py-3 text-sm font-semibold uppercase tracking-[0.2em] transition disabled:opacity-50 ${
        tone === "secondary"
          ? "border border-slate-700 bg-slate-900/80 text-slate-100 hover:border-slate-500"
          : "border border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-600"
      }`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

function StatusPill({ label }: { label: string }) {
  return (
    <div className="rounded-full border border-slate-700 bg-slate-900/70 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-200">
      {label}
    </div>
  );
}

function CandidateBreakdownTable({ results }: { results: OptimizationResponse | null }) {
  if (!results?.candidateSummary.length) {
    return (
      <EmptyMessage>
        Candidate topology metrics will appear here after the first concept generation.
      </EmptyMessage>
    );
  }

  return (
    <div className="overflow-hidden rounded-[24px] border border-slate-300 bg-white">
      <div className="grid grid-cols-[0.95fr_0.9fr_0.8fr_0.9fr_1fr] gap-3 border-b border-slate-200 px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">
        <span>Topology</span>
        <span>Tested</span>
        <span>Lots</span>
        <span>Road</span>
        <span>Status</span>
      </div>
      <div className="divide-y divide-slate-200">
        {results.candidateSummary.map((candidate) => (
          <div
            key={candidate.topology}
            className="grid grid-cols-[0.95fr_0.9fr_0.8fr_0.9fr_1fr] gap-3 px-4 py-3 text-sm text-slate-700"
          >
            <span className="font-semibold capitalize text-slate-900">{candidate.topology}</span>
            <span>{candidate.candidatesTested}</span>
            <span>{candidate.lots}</span>
            <span>{Math.round(candidate.roadLength)} ft</span>
            <span className="capitalize text-cyan-700">{candidate.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SavedRunCard({ run }: { run: RunSummary }) {
  return (
    <Link
      href={`/runs/${run.runId}`}
      className="block rounded-[22px] border border-slate-300 bg-white px-4 py-4 text-sm text-slate-700 transition hover:border-slate-500"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-semibold capitalize text-slate-900">{run.winningTopology}</span>
        <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-700">
          {run.lotCount} lots
        </span>
      </div>
      <div className="mt-2 text-slate-600">{run.parcelApn ?? run.parcelId}</div>
      <div className="mt-2 text-[11px] uppercase tracking-[0.22em] text-slate-500">
        {new Date(run.createdAt).toLocaleString()}
      </div>
    </Link>
  );
}

function EmptyMessage({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-[22px] border border-dashed border-slate-300 bg-white/60 px-4 py-5 text-sm text-slate-500">
      {children}
    </div>
  );
}
