"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { PlanSvgCanvas } from "@/components/studio/PlanSvgCanvas";
import { fetchRun } from "@/lib/api";

interface RunProps {
  params: { runId: string };
}

const layerOptions = ["parcel", "road", "easements", "lots", "lot_labels"] as const;

export default function RunPage({ params }: RunProps) {
  const runQuery = useQuery({
    queryKey: ["run", params.runId],
    queryFn: () => fetchRun(params.runId),
  });
  const [visibleLayers, setVisibleLayers] = useState<(typeof layerOptions)[number][]>([...layerOptions]);

  const run = runQuery.data;
  const response = run?.response;
  const fallbackUsed =
    Boolean(response?.winningTopology) &&
    Boolean(run?.topologyPreferences?.length) &&
    !run?.strictTopology &&
    !run.topologyPreferences.includes(response.winningTopology);
  return (
    <div className="grid h-[calc(100vh-72px)] overflow-hidden grid-cols-[320px_minmax(0,1fr)_380px]">
      <aside className="overflow-y-auto border-r border-slate-800 bg-slate-950/75 p-5">
        <Panel title="Saved run">
          <h1 className="text-xl font-semibold text-slate-100">{params.runId}</h1>
          <div className="mt-4 space-y-2 text-sm text-slate-300">
            <p>Parcel ID: {run?.parcelId ?? "Loading..."}</p>
            <p>County: {run?.parcel?.county ?? "—"}</p>
            <p>APN: {run?.parcel?.apn ?? "—"}</p>
            <p>Status: {run?.status ?? "Loading..."}</p>
            <p>Saved: {run?.createdAt ? new Date(run.createdAt).toLocaleString() : "—"}</p>
          </div>
          {run?.parcelId ? (
            <Link
              href={`/studio/${run.parcelId}`}
              className="mt-4 inline-flex rounded-2xl border border-cyan-400/40 px-4 py-2 text-sm font-semibold text-cyan-300"
            >
              Open parcel in Studio
            </Link>
          ) : null}
        </Panel>

        <Panel title="Run inputs">
          {"conceptText" in (run?.inputConstraints ?? {}) ? (
            <div className="mb-4 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4 text-sm leading-7 text-slate-200">
              {String(run?.inputConstraints?.conceptText ?? "")}
            </div>
          ) : null}
          <div className="space-y-2 text-sm text-slate-300">
            {Object.entries(run?.inputConstraints ?? {})
              .filter(([key]) => !["conceptText", "conceptInstruction", "conceptSummary"].includes(key))
              .map(([key, value]) => (
                <div key={key} className="flex justify-between gap-3 rounded-xl bg-slate-950/60 px-3 py-2">
                  <span className="text-slate-500">{key}</span>
                  <span>{String(value)}</span>
                </div>
              ))}
          </div>
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-3 text-sm text-slate-300">
            Topologies: {(run?.topologyPreferences ?? []).join(", ") || "all"}
            <br />
            Strict mode: {run?.strictTopology ? "enabled" : "disabled"}
          </div>
          {run?.response?.conceptSummary || run?.inputConstraints?.conceptSummary ? (
            <div className="mt-4 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-3 py-3 text-sm text-emerald-100">
              {String(run?.response?.conceptSummary ?? run?.inputConstraints?.conceptSummary ?? "")}
            </div>
          ) : null}
        </Panel>

        <Panel title="Layer controls">
          <div className="grid grid-cols-2 gap-2">
            {layerOptions.map((layer) => {
              const active = visibleLayers.includes(layer);
              return (
                <button
                  key={layer}
                  className={`rounded-2xl border px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] ${
                    active
                      ? "border-emerald-400/50 bg-emerald-400/10 text-emerald-300"
                      : "border-slate-700 text-slate-400"
                  }`}
                  onClick={() =>
                    setVisibleLayers((current) =>
                      current.includes(layer)
                        ? current.filter((item) => item !== layer)
                        : [...current, layer]
                    )
                  }
                >
                  {layer.replace("_", " ")}
                </button>
              );
            })}
          </div>
        </Panel>

        <Link
          href="/runs"
          className="mt-4 inline-flex rounded-2xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
        >
          Back to run history
        </Link>
      </aside>

      <section className="min-h-0 border-r border-slate-800 bg-[#dde4e8]">
        <PlanSvgCanvas
          parcel={run?.parcel}
          result={response ?? null}
          visibleLayers={visibleLayers}
          resetNonce={0}
        />
      </section>

      <aside className="overflow-y-auto bg-slate-950/85 p-5">
        <Panel title="Summary">
          <div className="space-y-2 text-sm text-slate-300">
            <p>Winning topology: {response?.winningTopology ?? "—"}</p>
            <p>Lot yield: {response?.lotCount ?? "—"}</p>
            <p>Parcel area: {response?.parcelAreaSqft?.toLocaleString() ?? "—"} sqft</p>
            <p>Developable area: {response?.developableAreaSqft?.toLocaleString() ?? "—"} sqft</p>
            <p>Road length: {response?.roadLengthFt?.toLocaleString() ?? "—"} ft</p>
            <p>Average lot size: {response?.averageLotAreaSqft?.toLocaleString() ?? "—"} sqft</p>
          </div>
          {fallbackUsed ? (
            <div className="mt-4 rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
              This saved run used fallback selection because a non-preferred topology produced the
              best feasible yield.
            </div>
          ) : null}
        </Panel>

        <Panel title="Topology breakdown">
          <div className="space-y-3">
            {(response?.candidateSummary ?? []).map((candidate) => (
              <div
                key={candidate.topology}
                className="rounded-2xl border border-slate-800 bg-slate-950/70 p-3 text-sm text-slate-300"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold capitalize text-slate-100">{candidate.topology}</span>
                  <span className="text-xs uppercase tracking-[0.24em] text-emerald-300">
                    {candidate.status}
                  </span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-400">
                  <span>tested: {candidate.candidatesTested}</span>
                  <span>lots: {candidate.lots}</span>
                  <span>road: {candidate.roadLength.toFixed(0)} ft</span>
                  <span>developable: {candidate.developableAreaSqft.toFixed(0)} sqft</span>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Exports">
          <div className="space-y-2">
            {response?.exports
              ? Object.entries(response.exports)
                  .filter(([, url]) => Boolean(url))
                  .map(([label, url]) => (
                    <a
                      key={label}
                      href={String(url)}
                      className="block rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-300"
                      target="_blank"
                      rel="noreferrer"
                    >
                      Download {label.toUpperCase()}
                    </a>
                  ))
              : <p className="text-sm text-slate-500">Loading exports...</p>}
          </div>
        </Panel>
      </aside>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4 rounded-[24px] border border-slate-800 bg-slate-900/70 p-5">
      <div className="mb-4 text-xs uppercase tracking-[0.32em] text-slate-500">{title}</div>
      {children}
    </section>
  );
}
