"use client";

import type { PipelineRun } from "@/lib/parcels";

import { StatusRow, WorkspaceSection } from "./shared";

export function FeasibilityStatePanel({ resolvedRun }: { resolvedRun: PipelineRun | null }) {
  if (!resolvedRun) {
    return (
      <WorkspaceSection eyebrow="Feasibility state" title="What worked and what failed">
        <p className="text-sm leading-7 text-slate-400">
          Run the pipeline to see which stages succeeded and whether the parcel completed or stopped at a constraint boundary.
        </p>
      </WorkspaceSection>
    );
  }

  const worked = buildWorkedList(resolvedRun);
  const failed = buildFailedList(resolvedRun);

  return (
    <WorkspaceSection eyebrow="Feasibility state" title="What worked and what failed">
      <div className="space-y-3 text-sm text-slate-300">
        <StatusRow label="Pipeline status" value={resolvedRun.status.replace(/_/g, " ")} />
        <StatusRow
          label="What worked"
          value={worked.length ? worked.join(" • ") : "No completed stages recorded"}
        />
        <StatusRow
          label="What failed"
          value={failed.length ? failed.join(" • ") : "No failed stages recorded"}
        />
      </div>
      {resolvedRun.stage_runtimes && Object.keys(resolvedRun.stage_runtimes).length ? (
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
  );
}

function buildWorkedList(run: PipelineRun) {
  const items = ["parcel loaded", "zoning attached"];
  if (run.layout_result) {
    items.push("layout generated");
  }
  if (run.feasibility_result) {
    items.push("economics evaluated");
  }
  return items;
}

function buildFailedList(run: PipelineRun) {
  if (run.status === "completed") {
    return ["no blocking failure"];
  }
  if (run.near_feasible_result?.reason_category) {
    return [run.near_feasible_result.reason_category.replace(/_/g, " ")];
  }
  if (run.bypass_reason) {
    return [run.bypass_reason.replace(/_/g, " ")];
  }
  return ["pipeline stopped before completion"];
}
