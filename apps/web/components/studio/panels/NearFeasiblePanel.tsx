"use client";

import type { NearFeasibleResult, PipelineRun } from "@/lib/parcels";

import { StatusRow, WorkspaceSection } from "./shared";

type NearFeasibleDisposition =
  | "true_no_go"
  | "conditional_upside"
  | "variance_play"
  | "geometry_cleanup";

export function NearFeasiblePanel({ resolvedRun }: { resolvedRun: PipelineRun | null }) {
  if (!resolvedRun || resolvedRun.status === "completed") {
    return null;
  }

  const nearFeasible = resolvedRun.near_feasible_result;
  const disposition = classifyNearFeasible(nearFeasible);
  const summary = buildNearFeasibleSummary(resolvedRun, nearFeasible, disposition);
  const pursuitGuidance = buildPursuitGuidance(disposition);

  return (
    <WorkspaceSection eyebrow="Near feasible" title="Is this still worth pursuing?">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <DispositionBadge disposition={disposition} />
          <StatusBadge label={resolvedRun.status.replace(/_/g, " ")} />
        </div>

        <p className="text-sm leading-7 text-slate-300">{summary}</p>

        <div className="grid gap-3">
          <StatusRow label="Why this did not complete" value={buildReasonLabel(resolvedRun, nearFeasible)} />
          <StatusRow label="Acquisition read" value={pursuitGuidance} />
          <StatusRow label="District" value={resolvedRun.zoning_result.district} />
        </div>
      </div>

      {nearFeasible ? (
        <div className="mt-5 grid gap-5">
          <ReadableBlock
            title="What is limiting this parcel"
            description="These are the concrete constraints preventing the current parcel from fully completing the pipeline."
            rows={describeConstraints(nearFeasible.limiting_constraints)}
            emptyLabel="No limiting constraints were returned."
          />
          <ReadableBlock
            title="What would need to change"
            description="These are the minimum relaxations or corrections required to move the parcel forward."
            rows={describeRelaxation(nearFeasible.required_relaxation)}
            emptyLabel="No explicit relaxation was returned."
          />
          <ReadableBlock
            title="What the best attempt looked like"
            description="This is the strongest candidate the engine found before it stopped."
            rows={describeBestAttempt(nearFeasible.best_attempt_summary)}
            emptyLabel="No best attempt summary was returned."
          />
          <ReadableBlock
            title="What upside exists if resolved"
            description="This is the estimated financial upside if the blocking constraint is addressed."
            rows={describeUpside(nearFeasible.financial_upside ?? {})}
            emptyLabel="No financial upside estimate was returned."
          />
          <div className="rounded-[22px] border border-slate-800 bg-slate-950/50 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
              Attempted strategies
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {nearFeasible.attempted_strategies.length ? (
                nearFeasible.attempted_strategies.map((strategy) => (
                  <span
                    key={strategy}
                    className="rounded-full border border-slate-700 px-3 py-1 text-xs font-medium text-slate-200"
                  >
                    {strategy.replace(/_/g, " ")}
                  </span>
                ))
              ) : (
                <span className="text-sm text-slate-500">No strategies recorded.</span>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-5 rounded-[22px] border border-dashed border-slate-700 px-4 py-5 text-sm text-slate-500">
          No structured near-feasible payload was returned for this parcel.
        </div>
      )}
    </WorkspaceSection>
  );
}

function ReadableBlock({
  title,
  description,
  rows,
  emptyLabel,
}: {
  title: string;
  description: string;
  rows: Array<{ label: string; value: string }>;
  emptyLabel: string;
}) {
  return (
    <div className="rounded-[22px] border border-slate-800 bg-slate-950/50 p-4">
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{title}</div>
      <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
      {rows.length ? (
        <dl className="mt-4 grid gap-3">
          {rows.map((row) => (
            <div
              key={`${row.label}:${row.value}`}
              className="grid gap-2 rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 md:grid-cols-[220px_1fr]"
            >
              <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                {row.label}
              </dt>
              <dd className="text-sm leading-6 text-slate-200">{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <div className="mt-4 text-sm text-slate-500">{emptyLabel}</div>
      )}
    </div>
  );
}

function classifyNearFeasible(nearFeasible: NearFeasibleResult | null | undefined): NearFeasibleDisposition {
  const reason = nearFeasible?.reason_category ?? "";
  const relaxationKeys = Object.keys(nearFeasible?.required_relaxation ?? {});
  if (reason.includes("GEOMETRY")) {
    return "geometry_cleanup";
  }
  if (relaxationKeys.some((key) => /setback|frontage|height|coverage|lot_area|min_lot/i.test(key))) {
    return "variance_play";
  }
  if (reason.includes("ZONING") || relaxationKeys.length > 0) {
    return "conditional_upside";
  }
  return "true_no_go";
}

function buildNearFeasibleSummary(
  run: PipelineRun,
  nearFeasible: NearFeasibleResult | null | undefined,
  disposition: NearFeasibleDisposition
) {
  const reason = buildReasonLabel(run, nearFeasible);
  const upside = describeUpside(nearFeasible?.financial_upside ?? {});
  const upsideSummary = upside.length ? upside[0]?.value : null;

  if (disposition === "variance_play") {
    return `This parcel is not a clean by-right deal. It looks more like a variance or rezoning play because ${reason.toLowerCase()}. ${
      upsideSummary ? `If resolved, the current model suggests ${upsideSummary.toLowerCase()}.` : ""
    }`.trim();
  }
  if (disposition === "geometry_cleanup") {
    return `This parcel appears blocked by geometry quality or shape constraints rather than simple economics. ${reason}. ${
      upsideSummary ? `If the geometry issue is resolved, the current model suggests ${upsideSummary.toLowerCase()}.` : ""
    }`.trim();
  }
  if (disposition === "conditional_upside") {
    return `This parcel has conditional upside, but it does not work under the current rule set. ${reason}. ${
      upsideSummary ? `If the blocking constraint changes, the model suggests ${upsideSummary.toLowerCase()}.` : ""
    }`.trim();
  }
  return `This parcel did not complete under the current assumptions and currently reads closer to a no-go. ${reason}.`;
}

function buildPursuitGuidance(disposition: NearFeasibleDisposition) {
  if (disposition === "variance_play") {
    return "Worth pursuing only if a zoning variance, frontage adjustment, or similar entitlement path is realistic.";
  }
  if (disposition === "geometry_cleanup") {
    return "Pursue only if the parcel geometry or source data can be corrected without changing the underlying land economics.";
  }
  if (disposition === "conditional_upside") {
    return "Potentially worth pursuing if the identified constraint can be relaxed at low entitlement risk.";
  }
  return "Current signal is closer to pass than pursue unless new information materially changes the constraint picture.";
}

function buildReasonLabel(run: PipelineRun, nearFeasible: NearFeasibleResult | null | undefined) {
  if (nearFeasible?.reason_category) {
    return nearFeasible.reason_category.replace(/_/g, " ");
  }
  if (run.bypass_reason) {
    return run.bypass_reason.replace(/_/g, " ");
  }
  return "pipeline failure";
}

function describeConstraints(data: Record<string, unknown>) {
  return Object.entries(data ?? {}).map(([key, value]) => ({
    label: humanizeKey(key),
    value: describeValue(key, value),
  }));
}

function describeRelaxation(data: Record<string, unknown>) {
  return Object.entries(data ?? {}).map(([key, value]) => ({
    label: humanizeKey(key),
    value: describeRelaxationValue(key, value),
  }));
}

function describeBestAttempt(data: Record<string, unknown>) {
  return Object.entries(data ?? {}).map(([key, value]) => ({
    label: humanizeKey(key),
    value: describeValue(key, value),
  }));
}

function describeUpside(data: Record<string, unknown>) {
  return Object.entries(data ?? {}).map(([key, value]) => ({
    label: humanizeKey(key),
    value: describeValue(key, value),
  }));
}

function describeRelaxationValue(key: string, value: unknown) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    const current = formatValue(record.current);
    const needed = formatValue(record.needed);
    const reduction = formatValue(record.reduction_sqft ?? record.reduction_ft ?? record.reduction);
    const pieces = [`current ${current}`, `needed ${needed}`];
    if (reduction !== "—" && reduction !== "0") {
      pieces.push(`change ${reduction}`);
    }
    return pieces.join(" • ");
  }
  return describeValue(key, value);
}

function describeValue(key: string, value: unknown) {
  if (typeof value === "number") {
    if (/roi/i.test(key)) {
      return `${(value * 100).toFixed(1)}%`;
    }
    if (/profit|revenue|cost|price|value/i.test(key)) {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      }).format(value);
    }
    if (/sqft|area/i.test(key)) {
      return `${Math.round(value).toLocaleString()} sqft`;
    }
    if (/frontage|setback|height|length|width|ft/i.test(key)) {
      return `${value.toFixed(1)} ft`;
    }
  }
  return formatValue(value);
}

function humanizeKey(key: string) {
  return key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim();
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return String(value);
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.length ? value.map((entry) => formatValue(entry)).join(", ") : "—";
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function DispositionBadge({ disposition }: { disposition: NearFeasibleDisposition }) {
  const mapping: Record<NearFeasibleDisposition, { label: string; tone: string }> = {
    true_no_go: {
      label: "True no-go",
      tone: "border-rose-400/40 bg-rose-400/10 text-rose-300",
    },
    conditional_upside: {
      label: "Conditional upside",
      tone: "border-cyan-400/40 bg-cyan-400/10 text-cyan-300",
    },
    variance_play: {
      label: "Variance / rezoning play",
      tone: "border-amber-400/40 bg-amber-400/10 text-amber-300",
    },
    geometry_cleanup: {
      label: "Geometry cleanup case",
      tone: "border-violet-400/40 bg-violet-400/10 text-violet-300",
    },
  };
  const config = mapping[disposition];
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] ${config.tone}`}>
      {config.label}
    </span>
  );
}

function StatusBadge({ label }: { label: string }) {
  return (
    <span className="rounded-full border border-slate-700 bg-slate-900/70 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-slate-200">
      {label}
    </span>
  );
}
