"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { StudioCanvas, type StudioLayerKey } from "@/components/studio/StudioCanvas";
import {
  ensureBedrockParcel,
  exportBedrockLayout,
  fetchRun,
  fetchRuns,
  runBedrockLayoutSearch,
  runBedrockPipeline,
} from "@/lib/api";
import type { BasemapMode } from "@/lib/mapConfig";
import type { BedrockLayoutResult, BedrockParcel, BedrockZoningRules, PipelineRun } from "@/lib/parcels";
import {
  layoutVisualizationFromLayoutResult,
  layoutVisualizationFromPipelineRun,
  pipelineRunExplanation,
  pipelineRunStateLabel,
  pipelineRunUiState,
  studioParcelFromBedrock,
} from "@/lib/parcels";

const defaultVisibleLayers: StudioLayerKey[] = ["parcel", "road", "lots", "lot_labels"];
const DEFAULT_DESIGN_TEMPLATE = {
  minLotSizeSqft: 6000,
  frontSetbackFt: 25,
  sideSetbackFt: 8,
  rearSetbackFt: 20,
  maxUnitsPerAcre: 5,
  roadWidthFt: 32,
  lotFrontageFt: 50,
  blockDepthFt: 110,
  internalOffsetFt: 0,
  strategy: "grid" as DesignStrategy,
};
const DESIGN_REGEN_DEBOUNCE_MS = 350;
const STRATEGY_PRESETS: Record<DesignStrategy, Partial<typeof DEFAULT_DESIGN_TEMPLATE>> = {
  grid: {
    minLotSizeSqft: 6000,
    maxUnitsPerAcre: 5,
    roadWidthFt: 30,
    lotFrontageFt: 48,
    blockDepthFt: 110,
    internalOffsetFt: 0,
  },
  spine: {
    minLotSizeSqft: 6500,
    maxUnitsPerAcre: 4.5,
    roadWidthFt: 34,
    lotFrontageFt: 56,
    blockDepthFt: 120,
    internalOffsetFt: 2,
  },
  cul_de_sac: {
    minLotSizeSqft: 7200,
    maxUnitsPerAcre: 4,
    roadWidthFt: 38,
    lotFrontageFt: 62,
    blockDepthFt: 125,
    internalOffsetFt: 4,
  },
};

type DesignStrategy = "grid" | "spine" | "cul_de_sac";
type DesignTemplate = typeof DEFAULT_DESIGN_TEMPLATE;
type DesignStandard = NonNullable<BedrockZoningRules["standards"]>[number];
type PromptDerivation = {
  effectiveTemplate: DesignTemplate;
  summary: string[];
  unsupported: string[];
};

type DesignRequestState = {
  template: DesignTemplate;
  zoning: BedrockZoningRules;
  payload: {
    parcel: BedrockParcel;
    zoning: BedrockZoningRules;
    max_candidates: number;
  };
};

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
  const [designTemplate, setDesignTemplate] = useState(DEFAULT_DESIGN_TEMPLATE);
  const [designPrompt, setDesignPrompt] = useState("");
  const [designLayout, setDesignLayout] = useState<BedrockLayoutResult | null>(null);
  const [designError, setDesignError] = useState<string | null>(null);
  const [designing, setDesigning] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportingDxf, setExportingDxf] = useState(false);
  const [designModeActive, setDesignModeActive] = useState(false);
  const [designRequestCount, setDesignRequestCount] = useState(0);
  const [lastDesignRequestAt, setLastDesignRequestAt] = useState<string | null>(null);
  const [lastRequestPayload, setLastRequestPayload] = useState<Record<string, unknown> | null>(null);
  const designRequestIdRef = useRef(0);

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
  const promptDerivation = useMemo(
    () => derivePromptAdjustedTemplate(designTemplate, designPrompt),
    [designPrompt, designTemplate]
  );
  const designRequestState = useMemo<DesignRequestState | null>(() => {
    if (!parcel) return null;
    const zoning = buildDesignModeZoning(parcel, promptDerivation.effectiveTemplate, designPrompt);
    return {
      template: promptDerivation.effectiveTemplate,
      zoning,
      payload: {
        parcel,
        zoning,
        max_candidates: 50,
      },
    };
  }, [designPrompt, parcel, promptDerivation.effectiveTemplate]);
  const visualization = designLayout
    ? layoutVisualizationFromLayoutResult(
        designLayout,
        parcel,
        "design-mode",
        designRequestState?.zoning
      )
    : resolvedRun
      ? layoutVisualizationFromPipelineRun(resolvedRun, parcel)
      : null;
  const runState = pipelineRunUiState(resolvedRun);
  const decisionSummary = pipelineRunExplanation(resolvedRun);
  const activeLayoutId = designLayout?.layout_id ?? visualization?.layoutId ?? null;
  const activeLotCount = designLayout?.unit_count ?? visualization?.lotCount ?? null;
  const activeRoadLengthFt = designLayout?.road_length_ft ?? visualization?.roadLengthFt ?? null;

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

  function handleDesignTemplateChange(field: keyof typeof DEFAULT_DESIGN_TEMPLATE, value: number) {
    setDesignModeActive(true);
    setDesignTemplate((current) => ({
      ...current,
      [field]: Number.isFinite(value) ? Math.max(0, value) : current[field],
    }));
  }

  function handleStrategyChange(strategy: DesignStrategy) {
    const preset = STRATEGY_PRESETS[strategy];
    setDesignTemplate((current) => ({
      ...current,
      ...preset,
      strategy,
    }));
    setDesignModeActive(true);
  }

  async function handleDesignLayout(requestState: DesignRequestState | null = designRequestState) {
    if (!requestState) return null;
    const requestId = designRequestIdRef.current + 1;
    designRequestIdRef.current = requestId;
    setDesigning(true);
    setDesignError(null);
    setLastRequestPayload(requestState.payload as Record<string, unknown>);
    try {
      const layout = await runBedrockLayoutSearch(requestState.payload);
      if (designRequestIdRef.current === requestId) {
        setDesignLayout(layout);
        setDesignRequestCount((current) => current + 1);
        setLastDesignRequestAt(new Date().toISOString());
      }
      return layout;
    } catch (error) {
      if (designRequestIdRef.current === requestId) {
        setDesignError(error instanceof Error ? error.message : "Direct layout generation failed.");
      }
    } finally {
      if (designRequestIdRef.current === requestId) {
        setDesigning(false);
      }
    }
    return null;
  }

  useEffect(() => {
    if (!designModeActive || !designRequestState) return;
    const timer = window.setTimeout(() => {
      void handleDesignLayout(designRequestState);
    }, DESIGN_REGEN_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [designModeActive, designRequestState]);

  function handleExportGeoJson() {
    if (!visualization?.resultGeoJSON || !activeLayoutId) return;
    const blob = new Blob([JSON.stringify(visualization.resultGeoJSON, null, 2)], {
      type: "application/geo+json",
    });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `${activeLayoutId}.geojson`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(objectUrl);
  }

  async function handleExportDxf() {
    if (!parcel) return;
    const layoutToExport = designLayout ?? resolvedRun?.layout_result ?? null;
    if (!layoutToExport) return;
    setExportingDxf(true);
    setExportError(null);
    try {
      const zoning = designLayout ? designRequestState?.zoning : resolvedRun?.zoning_result;
      const { blob, filename } = await exportBedrockLayout({
        parcel,
        layout: layoutToExport,
        zoning,
        format: "dxf",
      });
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "DXF export failed.");
    } finally {
      setExportingDxf(false);
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
          <button
            className="mt-3 w-full rounded-[24px] border border-cyan-400/40 bg-transparent px-5 py-4 text-sm font-semibold uppercase tracking-[0.24em] text-cyan-200 transition hover:border-cyan-300 hover:text-cyan-100 disabled:opacity-50"
            onClick={() => {
              setDesignModeActive(true);
              void handleDesignLayout(designRequestState);
            }}
            disabled={designing || parcelQuery.isLoading || !parcel}
          >
            {designing ? "Regenerating layout..." : designModeActive ? "Regenerate layout" : "Design Layout"}
          </button>
          {parcelQuery.isError ? (
            <Alert tone="error">{parcelQuery.error instanceof Error ? parcelQuery.error.message : "Parcel load failed."}</Alert>
          ) : null}
          {runError ? <Alert tone="error">{runError}</Alert> : null}
          {designError ? <Alert tone="error">{designError}</Alert> : null}
          {exportError ? <Alert tone="error">{exportError}</Alert> : null}
        </WorkspaceSection>

        <WorkspaceSection eyebrow="Design mode" title="Direct layout controls">
          <p className="text-sm leading-7 text-slate-300">
            Design Mode calls the canonical Bedrock layout engine directly. Once enabled, supported controls trigger a debounced
            <span className="mx-1 font-mono text-cyan-200">POST /layout/search</span>
            on every change, even when the parcel is non-buildable or unsupported in the strict pipeline.
          </p>
          <div className="mt-4 rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-300">
            <div className="flex items-center justify-between gap-3">
              <span className="text-slate-500">Interactive status</span>
              <span className="font-mono text-cyan-200">
                {designModeActive ? (designing ? "recomputing" : "live") : "idle"}
              </span>
            </div>
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="text-slate-500">Layout requests</span>
              <span className="font-mono text-slate-100">{designRequestCount}</span>
            </div>
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="text-slate-500">Last refresh</span>
              <span className="font-mono text-slate-100">
                {lastDesignRequestAt ? formatTimestamp(lastDesignRequestAt) : "—"}
              </span>
            </div>
          </div>

          <div className="mt-5 grid gap-3">
            <PromptInput
              value={designPrompt}
              onChange={(value) => {
                setDesignModeActive(true);
                setDesignPrompt(value);
              }}
              examples={[
                "maximize units with cul-de-sacs",
                "low density suburban layout",
                "wide roads, fewer lots",
              ]}
            />
            <StrategySelector value={designTemplate.strategy} onChange={handleStrategyChange} />
            {promptDerivation.summary.length ? (
              <div className="rounded-[20px] border border-cyan-500/20 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-cyan-300">
                  Prompt directives
                </div>
                <ul className="mt-2 space-y-1 text-cyan-100/90">
                  {promptDerivation.summary.map((item) => (
                    <li key={item}>• {item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {promptDerivation.unsupported.length ? (
              <div className="rounded-[20px] border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-amber-300">
                  Engine gaps
                </div>
                <ul className="mt-2 space-y-1">
                  {promptDerivation.unsupported.map((item) => (
                    <li key={item}>• {item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3">
            <NumericInput
              label="Min lot size"
              suffix="sqft"
              value={designTemplate.minLotSizeSqft}
              onChange={(value) => handleDesignTemplateChange("minLotSizeSqft", value)}
            />
            <NumericInput
              label="Max units / ac"
              value={designTemplate.maxUnitsPerAcre}
              step={0.5}
              onChange={(value) => handleDesignTemplateChange("maxUnitsPerAcre", value)}
            />
            <NumericInput
              label="Front setback"
              suffix="ft"
              value={designTemplate.frontSetbackFt}
              onChange={(value) => handleDesignTemplateChange("frontSetbackFt", value)}
            />
            <NumericInput
              label="Side setback"
              suffix="ft"
              value={designTemplate.sideSetbackFt}
              onChange={(value) => handleDesignTemplateChange("sideSetbackFt", value)}
            />
            <NumericInput
              label="Rear setback"
              suffix="ft"
              value={designTemplate.rearSetbackFt}
              onChange={(value) => handleDesignTemplateChange("rearSetbackFt", value)}
            />
            <NumericInput
              label="Road width"
              suffix="ft"
              value={designTemplate.roadWidthFt}
              onChange={(value) => handleDesignTemplateChange("roadWidthFt", value)}
            />
            <NumericInput
              label="Lot frontage"
              suffix="ft"
              value={designTemplate.lotFrontageFt}
              onChange={(value) => handleDesignTemplateChange("lotFrontageFt", value)}
            />
            <NumericInput
              label="Block depth"
              suffix="ft"
              value={designTemplate.blockDepthFt}
              onChange={(value) => handleDesignTemplateChange("blockDepthFt", value)}
              helper="Sent to /layout/search as an explicit block-depth hint."
            />
            <NumericInput
              label="Internal offset"
              suffix="ft"
              value={designTemplate.internalOffsetFt}
              onChange={(value) => handleDesignTemplateChange("internalOffsetFt", value)}
              helper="Applied as extra setbacks and parcel-edge buffer to pull lots inward."
            />
          </div>
          <div className="mt-4 rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-300">
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
              Effective layout request
            </div>
            <div className="mt-3 space-y-2">
              <StatusRow label="Strategy bias preset" value={designRequestState?.template.strategy.replace(/_/g, " ") ?? "—"} />
              <StatusRow
                label="Effective frontage"
                value={formatFeet(
                  computeEffectiveFrontage(
                    designRequestState?.template.minLotSizeSqft ?? promptDerivation.effectiveTemplate.minLotSizeSqft,
                    computeTargetLotDepth(
                      designRequestState?.template.blockDepthFt ?? promptDerivation.effectiveTemplate.blockDepthFt,
                      designRequestState?.template.internalOffsetFt ?? promptDerivation.effectiveTemplate.internalOffsetFt,
                      designRequestState?.template.frontSetbackFt ?? promptDerivation.effectiveTemplate.frontSetbackFt,
                      designRequestState?.template.rearSetbackFt ?? promptDerivation.effectiveTemplate.rearSetbackFt
                    ),
                    designRequestState?.template.lotFrontageFt ?? promptDerivation.effectiveTemplate.lotFrontageFt,
                    (designRequestState?.template.sideSetbackFt ?? promptDerivation.effectiveTemplate.sideSetbackFt) +
                      (designRequestState?.template.internalOffsetFt ?? promptDerivation.effectiveTemplate.internalOffsetFt)
                  )
                )}
              />
              <StatusRow
                label="Effective road width"
                value={formatFeet(designRequestState?.template.roadWidthFt ?? promptDerivation.effectiveTemplate.roadWidthFt)}
              />
            </div>
          </div>

              <div className="rounded-[18px] border border-slate-800 bg-slate-950/70 px-4 py-3 text-xs leading-6 text-slate-300">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
                  Studio debug
                </div>
                <div className="mt-3 space-y-2">
                  <StatusRow label="Recompute counter" value={String(designRequestCount)} mono />
                  <StatusRow label="Last layout ID" value={activeLayoutId ?? "—"} mono />
                </div>
                <pre className="mt-3 overflow-x-auto rounded-[14px] border border-slate-800 bg-slate-900/80 p-3 font-mono text-[11px] leading-5 text-cyan-100">
{JSON.stringify(lastRequestPayload, null, 2) ?? "null"}
                </pre>
              </div>
        </WorkspaceSection>

        <WorkspaceSection eyebrow="Pipeline status" title="Current analysis">
          <div className="space-y-3 text-sm text-slate-300">
            <StatusRow label="Parcel" value={parcel ? "loaded" : parcelQuery.isLoading ? "loading" : "unavailable"} />
            <StatusRow label="Run" value={resolvedRun ? resolvedRun.run_id : running ? "in progress" : "not started"} mono />
            <StatusRow label="Decision" value={pipelineRunStateLabel(resolvedRun)} />
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

      <section className="flex min-h-0 h-full border-r border-slate-300/60 bg-[#dde4e8]">
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
        <WorkspaceSection eyebrow="Decision" title="Parcel outcome">
          {resolvedRun ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <RunStateBadge run={resolvedRun} />
                <span className="text-xs uppercase tracking-[0.22em] text-slate-500">
                  {resolvedRun.status}
                </span>
              </div>
              <p className="text-sm leading-7 text-slate-300">{decisionSummary}</p>
            </div>
          ) : (
            <p className="text-sm leading-7 text-slate-400">
              Run the pipeline to determine whether this parcel is buildable, non-buildable, or unsupported.
            </p>
          )}
        </WorkspaceSection>

        <WorkspaceSection eyebrow="Feasibility" title="Return profile">
          {resolvedRun?.feasibility_result ? (
            <div className="space-y-3">
              <MetricCard label="Projected profit" value={formatCurrency(resolvedRun.feasibility_result.projected_profit)} />
              <MetricCard label="ROI" value={formatPercent(resolvedRun.feasibility_result.ROI)} />
              <MetricCard label="Revenue" value={formatCurrency(resolvedRun.feasibility_result.projected_revenue)} />
              <MetricCard label="Cost" value={formatCurrency(resolvedRun.feasibility_result.projected_cost)} />
              <MetricCard label="Units" value={String(resolvedRun.feasibility_result.units)} />
              <MetricCard label="Risk score" value={formatNumber(resolvedRun.feasibility_result.risk_score)} />
              <MetricCard label="Confidence" value={formatPercent(resolvedRun.feasibility_result.confidence)} />
            </div>
          ) : resolvedRun ? (
            <p className="text-sm leading-7 text-slate-400">
              Feasibility metrics are only available for buildable parcels that complete the full pipeline.
            </p>
          ) : (
            <p className="text-sm leading-7 text-slate-400">
              Run the pipeline to generate a canonical feasibility report for this parcel.
            </p>
          )}
        </WorkspaceSection>

        <WorkspaceSection eyebrow="Layout" title="Geometry summary">
          {visualization ? (
            <div className="space-y-3 text-sm text-slate-300">
              <StatusRow label="Source" value={designLayout ? "design mode" : "pipeline"} />
              <StatusRow label="Layout ID" value={activeLayoutId ?? "—"} mono />
              <StatusRow label="Lot count" value={activeLotCount !== null ? String(activeLotCount) : "—"} />
              <StatusRow
                label="Road length"
                value={activeRoadLengthFt !== null ? `${Math.round(activeRoadLengthFt).toLocaleString()} ft` : "—"}
              />
              <StatusRow label="Parcel area" value={visualization.parcelAreaSqft ? `${Math.round(visualization.parcelAreaSqft).toLocaleString()} sqft` : "—"} />
              <StatusRow label="Average lot size" value={visualization.averageLotAreaSqft ? `${visualization.averageLotAreaSqft.toLocaleString()} sqft` : "—"} />
            </div>
          ) : resolvedRun ? (
            <p className="text-sm leading-7 text-slate-400">
              No direct layout is loaded. Use Design Layout or run the strict pipeline.
            </p>
          ) : (
            <p className="text-sm leading-7 text-slate-400">
              The canvas will render direct layout output after you click Design Layout, even if the pipeline does not continue.
            </p>
          )}
          {visualization ? (
            <div className="mt-4 grid gap-3">
              <button
                className="w-full rounded-[18px] border border-cyan-400/50 bg-cyan-400/10 px-4 py-3 text-sm font-semibold uppercase tracking-[0.18em] text-cyan-100 transition hover:border-cyan-300 hover:text-cyan-50 disabled:opacity-50"
                onClick={() => void handleExportDxf()}
                disabled={exportingDxf || !parcel}
              >
                {exportingDxf ? "Exporting DXF..." : "Export DXF"}
              </button>
              <button
                className="w-full rounded-[18px] border border-slate-700 bg-slate-950/70 px-4 py-3 text-sm font-semibold uppercase tracking-[0.18em] text-slate-100 transition hover:border-cyan-400 hover:text-cyan-200"
                onClick={handleExportGeoJson}
              >
                Export GeoJSON
              </button>
              <div className="rounded-[18px] border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-xs leading-6 text-amber-100">
                Only DXF and GeoJSON export are available from this Studio flow. DWG and STEP are not exposed here.
              </div>
            </div>
          ) : null}
        </WorkspaceSection>

        {resolvedRun && runState !== "buildable" ? (
          <WorkspaceSection eyebrow="Explanation" title="Why this did not continue">
            <div className="space-y-3 text-sm text-slate-300">
              <StatusRow label="District" value={resolvedRun.zoning_result.district} />
              <StatusRow label="Reason" value={resolvedRun.bypass_reason ? resolvedRun.bypass_reason.replace(/_/g, " ") : "unsupported pipeline capability"} />
              <p className="leading-7 text-slate-400">
                The UI is showing the backend decision directly. This parcel did not continue into layout and feasibility because the current pipeline cannot support it safely.
              </p>
            </div>
          </WorkspaceSection>
        ) : null}

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

function RunStateBadge({ run }: { run: Pick<PipelineRun, "status"> }) {
  const tone =
    run.status === "completed"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
      : run.status === "non_buildable"
        ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
        : "border-rose-400/40 bg-rose-400/10 text-rose-300";
  const label = run.status === "completed" ? "Buildable" : run.status === "non_buildable" ? "Non-buildable" : "Unsupported";
  return <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] ${tone}`}>{label}</span>;
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

function NumericInput({
  label,
  value,
  onChange,
  suffix,
  step = 1,
  helper,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  suffix?: string;
  step?: number;
  helper?: string;
}) {
  return (
    <label className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-4">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-3 flex items-center gap-3">
        <input
          type="number"
          min={0}
          step={step}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
        />
        {suffix ? <span className="text-xs uppercase tracking-[0.2em] text-slate-500">{suffix}</span> : null}
      </div>
      {helper ? <div className="mt-2 text-xs leading-5 text-slate-500">{helper}</div> : null}
    </label>
  );
}

function buildDesignModeZoning(
  parcel: BedrockParcel,
  template: DesignTemplate,
  prompt = ""
): BedrockZoningRules {
  const effectiveSetbacks = {
    front: template.frontSetbackFt + template.internalOffsetFt,
    side: template.sideSetbackFt + template.internalOffsetFt,
    rear: template.rearSetbackFt + template.internalOffsetFt,
  };
  const effectiveBuildableDepthFt = computeTargetLotDepth(
    template.blockDepthFt,
    template.internalOffsetFt,
    template.frontSetbackFt,
    template.rearSetbackFt
  );
  const effectiveFrontage = computeEffectiveFrontage(
    template.minLotSizeSqft,
    effectiveBuildableDepthFt,
    template.lotFrontageFt,
    effectiveSetbacks.side
  );
  const standards = buildDesignModeStandards(
    parcel,
    template,
    effectiveSetbacks,
    effectiveFrontage,
    effectiveBuildableDepthFt
  );
  return {
    schema_name: "ZoningRules",
    schema_version: "1.0.0",
    parcel_id: parcel.parcel_id,
    jurisdiction: parcel.jurisdiction,
    district: parcel.zoning_district ?? "DESIGN-MODE",
    overlays: [],
    standards,
    setbacks: effectiveSetbacks,
    min_lot_size_sqft: template.minLotSizeSqft,
    max_units_per_acre: template.maxUnitsPerAcre,
    min_frontage_ft: effectiveFrontage,
    road_right_of_way_ft: template.roadWidthFt,
    citations: [
      "ui_design_mode_default_template",
      `strategy_preset:${template.strategy}`,
      `design_prompt:${prompt.trim() || "none"}`,
    ],
  };
}

function StrategySelector({
  value,
  onChange,
}: {
  value: DesignStrategy;
  onChange: (value: DesignStrategy) => void;
}) {
  const options: Array<{ value: DesignStrategy; label: string; note: string }> = [
    { value: "grid", label: "Grid bias", note: "tighter frontage and lighter roads" },
    { value: "spine", label: "Spine bias", note: "balanced frontage and central road bias" },
    { value: "cul_de_sac", label: "Cul-de-sac bias", note: "wider frontage and lower density preset" },
  ];
  return (
    <div className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-4">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Layout bias preset</div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        {options.map((option) => {
          const active = value === option.value;
          return (
            <button
              key={option.value}
              type="button"
              className={`rounded-[16px] border px-3 py-3 text-left transition ${
                active
                  ? "border-cyan-400/60 bg-cyan-400/10 text-cyan-100"
                  : "border-slate-700 bg-slate-900 text-slate-200 hover:border-slate-500"
              }`}
              onClick={() => onChange(option.value)}
            >
              <div className="text-xs font-semibold uppercase tracking-[0.16em]">{option.label}</div>
              <div className="mt-2 text-[11px] leading-5 text-slate-400">{option.note}</div>
            </button>
          );
        })}
      </div>
      <div className="mt-3 text-xs leading-5 text-slate-500">
        The current Bedrock API does not enforce a named strategy. These controls only bias supported request parameters
        before live search runs.
      </div>
    </div>
  );
}

function PromptInput({
  value,
  onChange,
  examples,
}: {
  value: string;
  onChange: (value: string) => void;
  examples: string[];
}) {
  return (
    <label className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-4">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Design prompt</div>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={3}
        placeholder="maximize units with cul-de-sacs"
        className="mt-3 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-3 text-sm text-slate-100"
      />
      <div className="mt-3 flex flex-wrap gap-2">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-300 transition hover:border-cyan-400 hover:text-cyan-100"
            onClick={() => onChange(example)}
          >
            {example}
          </button>
        ))}
      </div>
    </label>
  );
}

function derivePromptAdjustedTemplate(template: DesignTemplate, prompt: string): PromptDerivation {
  const normalized = prompt.trim().toLowerCase();
  let next: DesignTemplate = {
    ...STRATEGY_PRESETS[template.strategy],
    ...template,
    strategy: template.strategy,
  };
  if (!normalized) {
    return {
      effectiveTemplate: next,
      summary: [],
      unsupported: [],
    };
  }

  const summary: string[] = [];
  const unsupported: string[] = [];

  if (/\bcul[\s-]?de[\s-]?sac/.test(normalized)) {
    next = {
      ...next,
      ...STRATEGY_PRESETS.cul_de_sac,
      strategy: "cul_de_sac",
    };
    summary.push("prompt requests cul-de-sac bias");
  } else if (/\bspine\b/.test(normalized)) {
    next = {
      ...next,
      ...STRATEGY_PRESETS.spine,
      strategy: "spine",
    };
    summary.push("prompt requests spine-road bias");
  } else if (/\bgrid\b/.test(normalized)) {
    next = {
      ...next,
      ...STRATEGY_PRESETS.grid,
      strategy: "grid",
    };
    summary.push("prompt requests grid bias");
  }

  if (normalized.includes("maximize units")) {
    next.maxUnitsPerAcre = Math.max(next.maxUnitsPerAcre, 7);
    next.minLotSizeSqft = Math.max(4000, Math.min(next.minLotSizeSqft, 5000));
    summary.push("prompt increases density");
  }
  if (normalized.includes("low density") || normalized.includes("suburban")) {
    next.maxUnitsPerAcre = Math.min(next.maxUnitsPerAcre, 3.5);
    next.minLotSizeSqft = Math.max(next.minLotSizeSqft, 8000);
    next.lotFrontageFt = Math.max(next.lotFrontageFt, 70);
    summary.push("prompt reduces density and widens lots");
  }
  if (normalized.includes("wide roads")) {
    next.roadWidthFt = Math.max(next.roadWidthFt, 40);
    summary.push("prompt widens road right-of-way");
  }
  if (normalized.includes("fewer lots")) {
    next.maxUnitsPerAcre = Math.min(next.maxUnitsPerAcre, 3);
    next.minLotSizeSqft = Math.max(next.minLotSizeSqft, 9000);
    summary.push("prompt favors fewer lots");
  }
  if (normalized.includes("block depth")) {
    unsupported.push("natural-language block depth targeting is indirect until /layout/search exposes an explicit block-depth input");
  }
  if (normalized.includes("offset") || normalized.includes("padding")) {
    summary.push("prompt adds internal offset only through translated setbacks");
  }

  return {
    effectiveTemplate: next,
    summary,
    unsupported,
  };
}

function computeEffectiveFrontage(
  minLotSizeSqft: number,
  targetLotDepthFt: number,
  lotFrontageFt: number,
  sideSetbackFt: number
) {
  const requiredBuildableWidth = minLotSizeSqft / Math.max(targetLotDepthFt, 1);
  return Math.max(lotFrontageFt, requiredBuildableWidth + sideSetbackFt * 2);
}

function computeTargetLotDepth(
  blockDepthFt: number,
  internalOffsetFt: number,
  frontSetbackFt: number,
  rearSetbackFt: number
) {
  return Math.max(40, blockDepthFt - frontSetbackFt - rearSetbackFt - internalOffsetFt * 2);
}

function buildDesignModeStandards(
  parcel: BedrockParcel,
  template: DesignTemplate,
  effectiveSetbacks: { front: number; side: number; rear: number },
  effectiveFrontageFt: number,
  effectiveBuildableDepthFt: number
): DesignStandard[] {
  const district = parcel.zoning_district ?? "DESIGN-MODE";
  const standards: DesignStandard[] = [
    {
      id: `${district}:min_lot_size_sqft`,
      standard_type: "min_lot_size_sqft",
      value: template.minLotSizeSqft,
      units: "sqft",
    },
    {
      id: `${district}:max_units_per_acre`,
      standard_type: "max_units_per_acre",
      value: template.maxUnitsPerAcre,
      units: "du/ac",
    },
    {
      id: `${district}:front_setback_ft`,
      standard_type: "front_setback_ft",
      value: effectiveSetbacks.front,
      units: "ft",
    },
    {
      id: `${district}:side_setback_ft`,
      standard_type: "side_setback_ft",
      value: effectiveSetbacks.side,
      units: "ft",
    },
    {
      id: `${district}:rear_setback_ft`,
      standard_type: "rear_setback_ft",
      value: effectiveSetbacks.rear,
      units: "ft",
    },
    {
      id: `${district}:min_frontage_ft`,
      standard_type: "min_frontage_ft",
      value: effectiveFrontageFt,
      units: "ft",
    },
    {
      id: `${district}:lot_frontage_ft`,
      standard_type: "lot_frontage_ft",
      value: effectiveFrontageFt,
      units: "ft",
    },
    {
      id: `${district}:frontage_min_ft`,
      standard_type: "frontage_min_ft",
      value: effectiveFrontageFt,
      units: "ft",
    },
    {
      id: `${district}:road_right_of_way_ft`,
      standard_type: "road_right_of_way_ft",
      value: template.roadWidthFt,
      units: "ft",
    },
    {
      id: `${district}:layout_block_depth_ft`,
      standard_type: "layout_block_depth_ft",
      value: effectiveBuildableDepthFt,
      units: "ft",
    },
    {
      id: `${district}:easement_buffer_ft`,
      standard_type: "easement_buffer_ft",
      value: template.internalOffsetFt,
      units: "ft",
    },
  ];
  return standards;
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
