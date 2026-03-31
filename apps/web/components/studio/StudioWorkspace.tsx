"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { StudioCanvas, type StudioLayerKey } from "@/components/studio/StudioCanvas";
import { DecisionPanel } from "@/components/studio/panels/DecisionPanel";
import { FeasibilityPanel } from "@/components/studio/panels/FeasibilityPanel";
import { FeasibilityStatePanel } from "@/components/studio/panels/FeasibilityStatePanel";
import { LayoutPanel } from "@/components/studio/panels/LayoutPanel";
import { NearFeasiblePanel } from "@/components/studio/panels/NearFeasiblePanel";
import { ParcelHeader } from "@/components/studio/panels/ParcelHeader";
import { ProvenancePanel } from "@/components/studio/panels/ProvenancePanel";
import { RunControls } from "@/components/studio/panels/RunControls";
import { RunHistoryPanel } from "@/components/studio/panels/RunHistoryPanel";
import {
  ensureBedrockParcel,
  exportBedrockLayout,
  fetchRun,
  fetchRuns,
  runBedrockLayoutSearch,
  runBedrockOptimize,
  runBedrockPipeline,
} from "@/lib/api";
import type { BasemapMode } from "@/lib/mapConfig";
import type { BedrockLayoutResult, BedrockParcel, BedrockZoningRules, PipelineRun } from "@/lib/parcels";
import {
  layoutVisualizationFromLayoutResult,
  layoutVisualizationFromPipelineRun,
  pipelineRunExplanation,
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
  const [runSuccess, setRunSuccess] = useState<string | null>(null);
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
  const parcelHistoryQuery = useQuery({
    queryKey: ["studio-run-history", parcelRuns.map((run) => run.run_id).join(",")],
    queryFn: async () => Promise.all(parcelRuns.map((run) => fetchRun(run.run_id))),
    enabled: parcelRuns.length > 0,
    retry: false,
  });
  const latestRunQuery = useQuery({
    queryKey: ["studio-run", parcelRuns[0]?.run_id],
    queryFn: () => fetchRun(parcelRuns[0]!.run_id),
    enabled: Boolean(parcelRuns[0]?.run_id) && !activeRun,
    retry: false,
  });

  const parcel = parcelQuery.data ?? null;
  const studioParcel = parcel ? studioParcelFromBedrock(parcel) : null;
  const resolvedRun = activeRun ?? latestRunQuery.data ?? null;
  const parcelRunHistory = useMemo(
    () =>
      (parcelHistoryQuery.data ?? [])
        .filter((run) => run.parcel_id === parcelId)
        .sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp)),
    [parcelHistoryQuery.data, parcelId]
  );
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
    ? layoutVisualizationFromLayoutResult(designLayout, parcel, "design-mode", designRequestState?.zoning)
    : resolvedRun
      ? layoutVisualizationFromPipelineRun(resolvedRun, parcel)
      : null;
  const activeLayoutId = designLayout?.layout_id ?? visualization?.layoutId ?? null;
  const activeLotCount = designLayout?.unit_count ?? visualization?.lotCount ?? null;
  const activeRoadLengthFt = designLayout?.road_length_ft ?? visualization?.roadLengthFt ?? null;
  const strategyContext = designLayout
    ? `design mode • ${designTemplate.strategy.replace(/_/g, " ")}`
    : resolvedRun?.near_feasible_result?.attempted_strategies?.length
      ? resolvedRun.near_feasible_result.attempted_strategies.join(", ")
      : typeof resolvedRun?.layout_result?.metadata?.source_engine === "string"
        ? resolvedRun.layout_result.metadata.source_engine
        : null;

  async function handleRun() {
    if (!parcel) return;
    setRunning(true);
    setRunError(null);
    setRunSuccess(null);
    try {
      const run = await runBedrockPipeline(parcel);
      setActiveRun(run);
      setRunSuccess("Feasibility complete. This parcel is now available on the Opportunities surface.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["studio-runs"] }),
        queryClient.invalidateQueries({ queryKey: ["opportunities", "runs"] }),
        queryClient.invalidateQueries({ queryKey: ["runs-memory-index"] }),
      ]);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Pipeline execution failed.");
    } finally {
      setRunning(false);
    }
  }

  async function handleDeepEvaluate() {
    if (!parcel) return;
    setRunning(true);
    setRunError(null);
    setRunSuccess(null);
    try {
      const optimizationRun = await runBedrockOptimize(parcel);
      if (optimizationRun.selected_pipeline_run_id) {
        const run = await fetchRun(optimizationRun.selected_pipeline_run_id);
        setActiveRun(run);
      }
      const rec = optimizationRun.decision?.recommendation ?? "evaluated";
      setRunSuccess(`Deep evaluation complete. Recommendation: ${rec.replace(/_/g, " ")}. Open the Decision Report for full analysis.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["studio-runs"] }),
        queryClient.invalidateQueries({ queryKey: ["opportunities", "runs"] }),
        queryClient.invalidateQueries({ queryKey: ["runs-memory-index"] }),
        queryClient.invalidateQueries({ queryKey: ["optimization-runs"] }),
      ]);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Deep evaluation failed.");
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

  function handleStartDesign() {
    setDesignModeActive(true);
    void handleDesignLayout(designRequestState);
  }

  return (
    <div className="grid h-[calc(100vh-72px)] overflow-hidden grid-cols-1 bg-[#d6dde1] xl:grid-cols-[360px_minmax(0,1fr)_380px]">
      <aside className="border-r border-slate-800/80 bg-slate-950/96 p-5 xl:overflow-y-auto">
        <ParcelHeader
          title={studioParcel?.apn ?? parcelId}
          parcel={parcel}
          parcelId={parcelId}
          parcelLoading={parcelQuery.isLoading}
          runLoading={running}
          designLoading={designing}
          parcelError={parcelQuery.isError ? (parcelQuery.error instanceof Error ? parcelQuery.error.message : "Parcel load failed.") : null}
          runError={runError}
          runSuccess={runSuccess}
          designError={designError}
          exportError={exportError}
          onRun={() => void handleRun()}
          onDeepEvaluate={() => void handleDeepEvaluate()}
          onDesign={handleStartDesign}
          formatArea={formatArea}
        />
        <RunControls
          parcel={parcel}
          resolvedRun={resolvedRun}
          running={running}
          designModeActive={designModeActive}
          designing={designing}
          designPrompt={designPrompt}
          designTemplate={designTemplate}
          promptDerivation={promptDerivation}
          designRequestState={designRequestState}
          designRequestCount={designRequestCount}
          lastDesignRequestAt={lastDesignRequestAt}
          lastRequestPayload={lastRequestPayload}
          onPromptChange={(value) => {
            setDesignModeActive(true);
            setDesignPrompt(value);
          }}
          onStrategyChange={handleStrategyChange}
          onDesignTemplateChange={handleDesignTemplateChange}
          formatTimestamp={formatTimestamp}
        />
        <RunHistoryPanel runs={parcelRunHistory} formatTimestamp={formatTimestamp} />
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
        <DecisionPanel resolvedRun={resolvedRun} />
        <FeasibilityPanel resolvedRun={resolvedRun} />
        <FeasibilityStatePanel resolvedRun={resolvedRun} />
        <LayoutPanel
          parcel={parcel}
          resolvedRun={resolvedRun}
          visualization={visualization}
          activeLayoutId={activeLayoutId}
          activeLotCount={activeLotCount}
          activeRoadLengthFt={activeRoadLengthFt}
          designModeActive={Boolean(designLayout)}
          strategyContext={strategyContext}
          exportingDxf={exportingDxf}
          onExportDxf={() => void handleExportDxf()}
          onExportGeoJson={handleExportGeoJson}
        />
        <NearFeasiblePanel resolvedRun={resolvedRun} />
        <ProvenancePanel parcel={parcel} resolvedRun={resolvedRun} />
      </aside>
    </div>
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

function formatTimestamp(value: string) {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return value;
  return timestamp.toLocaleString();
}
