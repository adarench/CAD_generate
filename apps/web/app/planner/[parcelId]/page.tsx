"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { MapView } from "@/components/MapView";
import { fetchParcel } from "@/lib/api";
import type { OptimizationResponse } from "@/lib/parcels";
import { runOptimizationApi } from "@/lib/optimize";

interface PlannerProps {
  params: { parcelId: string };
}

const topologyOptions = ["parallel", "spine", "loop", "culdesac"] as const;
const layerOptions = ["parcel", "road", "easements", "lots", "lot_labels"] as const;

export default function PlannerPage({ params }: PlannerProps) {
  const parcelQuery = useQuery({
    queryKey: ["parcel", params.parcelId],
    queryFn: () => fetchParcel(params.parcelId),
  });

  const [selectedTopologies, setSelectedTopologies] = useState<string[]>([...topologyOptions]);
  const [strictTopology, setStrictTopology] = useState(false);
  const [constraints, setConstraints] = useState({
    minFrontage: 60,
    minDepth: 110,
    minArea: 6000,
    roadWidth: 40,
    easementWidth: 12,
    lotCount: 32,
    roadOrientation: "north_south" as const,
  });
  const [visibleLayers, setVisibleLayers] = useState<string[]>([...layerOptions]);
  const [results, setResults] = useState<OptimizationResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parcel = parcelQuery.data;
  const filteredResult = useMemo(() => {
    if (!results?.resultGeoJSON) return null;
    return {
      ...results.resultGeoJSON,
      features: results.resultGeoJSON.features.filter((feature) =>
        visibleLayers.includes(String(feature.properties?.layer))
      ),
    };
  }, [results, visibleLayers]);
  const fallbackUsed =
    Boolean(results?.winningTopology) &&
    selectedTopologies.length > 0 &&
    !selectedTopologies.includes(results.winningTopology);

  async function handleRun() {
    if (!parcel) return;
    setRunning(true);
    setError(null);
    try {
      const response = await runOptimizationApi(
        parcel,
        constraints,
        selectedTopologies.length ? selectedTopologies : ["all"],
        strictTopology
      );
      setResults(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Optimization failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="grid min-h-[calc(100vh-72px)] grid-cols-[340px_minmax(0,1fr)_380px]">
      <aside className="border-r border-slate-800 bg-slate-950/80 p-5">
        <Panel title="Parcel">
          <h1 className="text-xl font-semibold text-slate-100">{parcel?.apn ?? params.parcelId}</h1>
          <div className="mt-4 space-y-2 text-sm text-slate-300">
            <p>{parcel ? `${parcel.county} County` : "Loading parcel record..."}</p>
            <p>{parcel?.address ?? "No address available"}</p>
            <p>
              {parcel?.areaSqft?.toLocaleString() ?? "—"} sqft •{" "}
              {parcel?.areaAcres?.toFixed(2) ?? "—"} acres
            </p>
            <p className="text-slate-500">
              {parcel?.sourceProvider ?? "Waiting for parcel source"} • {parcel?.sourceDataset ?? "—"}
            </p>
          </div>
        </Panel>

        <Panel title="Design constraints">
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
            label="Road width"
            value={constraints.roadWidth}
            onChange={(value) => setConstraints({ ...constraints, roadWidth: value })}
          />
          <NumberField
            label="Easement width"
            value={constraints.easementWidth}
            onChange={(value) => setConstraints({ ...constraints, easementWidth: value })}
          />
          <NumberField
            label="Target lots"
            value={constraints.lotCount}
            onChange={(value) => setConstraints({ ...constraints, lotCount: value })}
          />
        </Panel>

        <Panel title="Topology preferences">
          <p className="mb-3 text-sm text-slate-400">
            Choose the street-network families to test. Strict mode blocks fallback to other
            topologies when no valid candidate exists.
          </p>
          <div className="flex flex-wrap gap-2">
            {topologyOptions.map((option) => {
              const active = selectedTopologies.includes(option);
              return (
                <button
                  key={option}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.2em] ${
                    active
                      ? "bg-emerald-400 text-slate-950"
                      : "border border-slate-700 text-slate-300"
                  }`}
                  onClick={() =>
                    setSelectedTopologies((current) =>
                      current.includes(option)
                        ? current.filter((item) => item !== option)
                        : [...current, option]
                    )
                  }
                >
                  {option}
                </button>
              );
            })}
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={strictTopology}
              onChange={(event) => setStrictTopology(event.target.checked)}
            />
            Strict topology mode
          </label>
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

        {error ? (
          <div className="mt-4 rounded-2xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
            {error}
          </div>
        ) : null}

        <button
          className="mt-4 w-full rounded-2xl bg-emerald-400 px-4 py-3 text-sm font-semibold uppercase tracking-[0.24em] text-slate-950 disabled:opacity-50"
          onClick={handleRun}
          disabled={running || !parcel}
        >
          {running ? "Optimizing..." : "Generate concept plan"}
        </button>
      </aside>

      <section className="min-h-[720px] border-r border-slate-800">
        <MapView
          parcelGeometry={parcel?.geometryGeoJSON ?? null}
          center={parcel?.centroid ?? null}
          resultGeoJSON={filteredResult}
        />
      </section>

      <aside className="bg-slate-950/85 p-5">
        <Panel title="Optimization summary">
          <h2 className="text-lg font-semibold text-slate-100">
            {results ? `${results.winningTopology} winner` : "Ready to optimize"}
          </h2>
          <div className="mt-4 space-y-2 text-sm text-slate-300">
            <p>Max lot count: {results?.lotCount ?? "—"}</p>
            <p>Parcel area: {results?.parcelAreaSqft?.toLocaleString() ?? "—"} sqft</p>
            <p>Developable area: {results?.developableAreaSqft?.toLocaleString() ?? "—"} sqft</p>
            <p>Road length: {results?.roadLengthFt?.toLocaleString() ?? "—"} ft</p>
            <p>Average lot size: {results?.averageLotAreaSqft?.toLocaleString() ?? "—"} sqft</p>
            <p>
              Preferred topologies: {selectedTopologies.length ? selectedTopologies.join(", ") : "all"}
            </p>
          </div>
          {fallbackUsed ? (
            <div className="mt-4 rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
              Fallback was used. The winning layout came from a non-preferred topology because
              strict mode is off.
            </div>
          ) : null}
          {results?.runId ? (
            <Link
              href={`/runs/${results.runId}`}
              className="mt-4 inline-flex rounded-2xl border border-emerald-400/40 px-4 py-2 text-sm font-semibold text-emerald-300"
            >
              Open saved run
            </Link>
          ) : null}
        </Panel>

        <Panel title="Candidate breakdown">
          <div className="grid grid-cols-[1fr_0.8fr_0.8fr_1fr] gap-2 px-2 text-[11px] uppercase tracking-[0.2em] text-slate-500">
            <span>Topology</span>
            <span>Tested</span>
            <span>Lots</span>
            <span>Status</span>
          </div>
          <div className="mt-3 space-y-2">
            {(results?.candidateSummary ?? []).map((candidate) => (
              <div
                key={candidate.topology}
                className="rounded-2xl border border-slate-800 bg-slate-950/70 px-3 py-3 text-sm text-slate-300"
              >
                <div className="grid grid-cols-[1fr_0.8fr_0.8fr_1fr] gap-2">
                  <span className="font-semibold capitalize text-slate-100">{candidate.topology}</span>
                  <span>{candidate.candidatesTested}</span>
                  <span>{candidate.lots}</span>
                  <span className="uppercase tracking-[0.18em] text-emerald-300">
                    {candidate.status}
                  </span>
                </div>
                <div className="mt-2 flex justify-between text-xs text-slate-500">
                  <span>Road: {candidate.roadLength.toFixed(0)} ft</span>
                  <span>Developable: {candidate.developableAreaSqft.toFixed(0)} sqft</span>
                </div>
                {candidate.notes ? <div className="mt-2 text-xs text-amber-300">{candidate.notes}</div> : null}
              </div>
            ))}
            {!results ? (
              <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-6 text-sm text-slate-500">
                Run the optimizer to compare topologies and yield.
              </div>
            ) : null}
          </div>
        </Panel>

        <Panel title="Exports">
          <div className="space-y-2 text-sm">
            {results?.exports ? (
              Object.entries(results.exports)
                .filter(([, url]) => Boolean(url))
                .map(([label, url]) => (
                  <a
                    key={label}
                    href={String(url)}
                    className="block rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-slate-300"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Download {label.toUpperCase()}
                  </a>
                ))
            ) : (
              <p className="text-sm text-slate-500">Exports will appear after a successful run.</p>
            )}
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
    <label className="mb-3 block text-sm text-slate-300">
      <span className="mb-1 block text-xs uppercase tracking-[0.22em] text-slate-500">{label}</span>
      <input
        className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-3 py-2"
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}
