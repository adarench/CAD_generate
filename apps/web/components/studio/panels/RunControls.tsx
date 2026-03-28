"use client";

import type { BedrockParcel, BedrockZoningRules, PipelineRun } from "@/lib/parcels";

import { Alert, NumericInput, StatusRow, WorkspaceSection } from "./shared";

type DesignStrategy = "grid" | "spine" | "cul_de_sac";

type DesignTemplate = {
  minLotSizeSqft: number;
  frontSetbackFt: number;
  sideSetbackFt: number;
  rearSetbackFt: number;
  maxUnitsPerAcre: number;
  roadWidthFt: number;
  lotFrontageFt: number;
  blockDepthFt: number;
  internalOffsetFt: number;
  strategy: DesignStrategy;
};

type DesignRequestState = {
  template: DesignTemplate;
  zoning: BedrockZoningRules;
  payload: {
    parcel: BedrockParcel;
    zoning: BedrockZoningRules;
    max_candidates: number;
  };
} | null;

type PromptDerivation = {
  effectiveTemplate: DesignTemplate;
  summary: string[];
  unsupported: string[];
};

export function RunControls({
  parcel,
  resolvedRun,
  running,
  designModeActive,
  designing,
  designPrompt,
  designTemplate,
  promptDerivation,
  designRequestState,
  designRequestCount,
  lastDesignRequestAt,
  lastRequestPayload,
  onPromptChange,
  onStrategyChange,
  onDesignTemplateChange,
  formatTimestamp,
}: {
  parcel: BedrockParcel | null;
  resolvedRun: PipelineRun | null;
  running: boolean;
  designModeActive: boolean;
  designing: boolean;
  designPrompt: string;
  designTemplate: DesignTemplate;
  promptDerivation: PromptDerivation;
  designRequestState: DesignRequestState;
  designRequestCount: number;
  lastDesignRequestAt: string | null;
  lastRequestPayload: Record<string, unknown> | null;
  onPromptChange: (value: string) => void;
  onStrategyChange: (value: DesignStrategy) => void;
  onDesignTemplateChange: (field: keyof DesignTemplate, value: number) => void;
  formatTimestamp: (value: string) => string;
}) {
  return (
    <>
      <WorkspaceSection eyebrow="Design mode" title="Direct layout controls">
        <p className="text-sm leading-7 text-slate-300">
          Design Mode calls the canonical Bedrock layout engine directly. Once enabled, supported controls trigger a debounced
          <span className="mx-1 font-mono text-cyan-200">POST /layout/search</span>
          on every change, even when the parcel is near-feasible or failed in the strict pipeline.
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
            onChange={onPromptChange}
            examples={[
              "maximize units with cul-de-sacs",
              "low density suburban layout",
              "wide roads, fewer lots",
            ]}
          />
          <StrategySelector value={designTemplate.strategy} onChange={onStrategyChange} />
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
          <NumericInput label="Min lot size" suffix="sqft" value={designTemplate.minLotSizeSqft} onChange={(value) => onDesignTemplateChange("minLotSizeSqft", value)} />
          <NumericInput label="Max units / ac" value={designTemplate.maxUnitsPerAcre} step={0.5} onChange={(value) => onDesignTemplateChange("maxUnitsPerAcre", value)} />
          <NumericInput label="Front setback" suffix="ft" value={designTemplate.frontSetbackFt} onChange={(value) => onDesignTemplateChange("frontSetbackFt", value)} />
          <NumericInput label="Side setback" suffix="ft" value={designTemplate.sideSetbackFt} onChange={(value) => onDesignTemplateChange("sideSetbackFt", value)} />
          <NumericInput label="Rear setback" suffix="ft" value={designTemplate.rearSetbackFt} onChange={(value) => onDesignTemplateChange("rearSetbackFt", value)} />
          <NumericInput label="Road width" suffix="ft" value={designTemplate.roadWidthFt} onChange={(value) => onDesignTemplateChange("roadWidthFt", value)} />
          <NumericInput label="Lot frontage" suffix="ft" value={designTemplate.lotFrontageFt} onChange={(value) => onDesignTemplateChange("lotFrontageFt", value)} />
          <NumericInput
            label="Block depth"
            suffix="ft"
            value={designTemplate.blockDepthFt}
            onChange={(value) => onDesignTemplateChange("blockDepthFt", value)}
            helper="Sent to /layout/search as an explicit block-depth hint."
          />
          <NumericInput
            label="Internal offset"
            suffix="ft"
            value={designTemplate.internalOffsetFt}
            onChange={(value) => onDesignTemplateChange("internalOffsetFt", value)}
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
            <StatusRow label="Parcel loaded" value={parcel ? "yes" : "no"} mono />
          </div>
          <pre className="mt-3 overflow-x-auto rounded-[14px] border border-slate-800 bg-slate-900/80 p-3 font-mono text-[11px] leading-5 text-cyan-100">
{JSON.stringify(lastRequestPayload, null, 2) ?? "null"}
          </pre>
        </div>
      </WorkspaceSection>

      <WorkspaceSection eyebrow="Pipeline status" title="Current analysis">
        <div className="space-y-3 text-sm text-slate-300">
          <StatusRow label="Parcel" value={parcel ? "loaded" : "unavailable"} />
          <StatusRow label="Run" value={resolvedRun ? resolvedRun.run_id : running ? "in progress" : "not started"} mono />
          <StatusRow label="Decision" value={resolvedRun ? (resolvedRun.status === "completed" ? "Buildable" : resolvedRun.status === "near_feasible" ? "Near-feasible" : "Failed") : "Not run"} />
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
    </>
  );
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

function formatFeet(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${value.toFixed(0)} ft`;
}
