"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { MapView } from "@/components/MapView";
import { fetchParcelByClick, fetchRecentParcels, searchParcelByApn } from "@/lib/api";
import type { ParcelRecord } from "@/lib/parcels";
import { SUPPORTED_UTAH_COUNTIES } from "@/services/parcels/arcgisParcelClient";

const counties = [...SUPPORTED_UTAH_COUNTIES];

export default function MapPage() {
  const router = useRouter();
  const recentParcels = useQuery({
    queryKey: ["recent-parcels-map"],
    queryFn: () => fetchRecentParcels(6),
  });
  const [selectedParcel, setSelectedParcel] = useState<ParcelRecord | null>(null);
  const [candidateParcels, setCandidateParcels] = useState<ParcelRecord[]>([]);
  const [apnQuery, setApnQuery] = useState("");
  const [county, setCounty] = useState<string>(counties[0]);
  const [error, setError] = useState<string | null>(null);
  const [lookupMessage, setLookupMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleApnSearch() {
    setLoading(true);
    setError(null);
    setLookupMessage(null);
    try {
      const matches = await searchParcelByApn(county, apnQuery);
      setSelectedParcel(matches[0] ?? null);
      setCandidateParcels(matches);
      if (matches.length > 1) {
        setLookupMessage("Multiple parcel matches returned for this APN. Review the candidate list.");
      }
      if (!matches.length) {
        setError("No parcel found for that county/APN combination.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Parcel search failed.");
      setCandidateParcels([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleMapClick(lat: number, lng: number) {
    setLoading(true);
    setError(null);
    setLookupMessage(null);
    try {
      const response = await fetchParcelByClick(lng, lat, county);
      setSelectedParcel(response.selected);
      setCandidateParcels(response.candidates);
      setLookupMessage(response.message ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Parcel lookup failed.");
      setCandidateParcels([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-72px)] flex-col">
      <div className="border-b border-slate-800 bg-slate-950/80 px-5 py-4">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-5">
          <div>
            <div className="text-xs uppercase tracking-[0.32em] text-slate-500">Parcel map</div>
            <h1 className="text-xl font-semibold text-slate-100">
              Live Utah parcel intake for subdivision feasibility
            </h1>
          </div>
          <div className="flex min-w-[560px] items-center gap-3 rounded-[24px] border border-slate-800 bg-slate-900/80 p-3">
            <select
              className="rounded-2xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              value={county}
              onChange={(event) => setCounty(event.target.value)}
            >
              {counties.map((entry) => (
                <option key={entry} value={entry}>
                  {entry} County
                </option>
              ))}
            </select>
            <input
              className="flex-1 rounded-2xl border border-slate-700 bg-slate-950 px-4 py-2 text-sm"
              placeholder="County-scoped APN"
              value={apnQuery}
              onChange={(event) => setApnQuery(event.target.value)}
            />
            <button
              className="rounded-2xl bg-emerald-400 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50"
              onClick={handleApnSearch}
              disabled={loading || !apnQuery.trim()}
            >
              {loading ? "Searching..." : "Find parcel"}
            </button>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[280px_minmax(0,1fr)_380px]">
        <aside className="border-r border-slate-800 bg-slate-950/75 p-5">
          <div className="rounded-[24px] border border-slate-800 bg-slate-900/70 p-5">
            <div className="text-xs uppercase tracking-[0.3em] text-slate-500">How to use</div>
            <div className="mt-4 space-y-3 text-sm text-slate-300">
              <p>1. Keep the county selector aligned with the parcel market you are reviewing.</p>
              <p>2. Search by APN or click the parcel directly on the map.</p>
              <p>3. Review the normalized parcel record, then launch the concept planner.</p>
            </div>
          </div>

          <div className="mt-4 rounded-[24px] border border-slate-800 bg-slate-900/70 p-5">
            <div className="text-xs uppercase tracking-[0.3em] text-slate-500">Recent parcels</div>
            <div className="mt-4 space-y-3">
              {(recentParcels.data ?? []).map((parcel) => (
                <button
                  key={parcel.id}
                  className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-left transition hover:border-slate-600"
                  onClick={() => {
                    setSelectedParcel(parcel);
                    setCandidateParcels([parcel]);
                    setLookupMessage("Loaded from the cached parcel history.");
                  }}
                >
                  <div className="font-semibold text-slate-100">{parcel.apn ?? parcel.id}</div>
                  <div className="mt-1 text-sm text-slate-400">
                    {parcel.county} County • {parcel.areaAcres?.toFixed(2) ?? "—"} acres
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4 rounded-[24px] border border-slate-800 bg-slate-900/70 p-5">
            <div className="text-xs uppercase tracking-[0.3em] text-slate-500">Candidate parcels</div>
            <div className="mt-4 space-y-3">
              {candidateParcels.length ? (
                candidateParcels.map((parcel) => {
                  const active = parcel.id === selectedParcel?.id;
                  return (
                    <button
                      key={parcel.id}
                      className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                        active
                          ? "border-emerald-400/50 bg-emerald-400/10"
                          : "border-slate-800 bg-slate-950/70 hover:border-slate-600"
                      }`}
                      onClick={() => setSelectedParcel(parcel)}
                    >
                      <div className="font-semibold text-slate-100">{parcel.apn ?? parcel.id}</div>
                      <div className="mt-1 text-sm text-slate-400">
                        {parcel.address ?? "Address unavailable"}
                      </div>
                      <div className="mt-1 text-xs uppercase tracking-[0.22em] text-slate-500">
                        {parcel.areaAcres?.toFixed(2) ?? "—"} acres
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-6 text-sm text-slate-500">
                  APN and point lookups that return more than one parcel will appear here.
                </div>
              )}
            </div>
          </div>

          {lookupMessage ? (
            <div className="mt-4 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 p-4 text-sm text-emerald-100">
              {lookupMessage}
            </div>
          ) : null}

          {error ? (
            <div className="mt-4 rounded-2xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
              {error}
            </div>
          ) : null}
        </aside>

        <section className="relative min-h-[720px]">
          <MapView
            onParcelClick={handleMapClick}
            parcelGeometry={selectedParcel?.geometryGeoJSON ?? null}
            center={selectedParcel?.centroid ?? null}
          />
          <div className="absolute left-5 top-5 rounded-full border border-slate-800 bg-slate-950/85 px-4 py-2 text-xs uppercase tracking-[0.24em] text-slate-400">
            {loading ? "Querying parcel source..." : `${county} County active`}
          </div>
        </section>

        <aside className="border-l border-slate-800 bg-slate-950/85 p-5">
          <div className="rounded-[28px] border border-slate-800 bg-slate-900/80 p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xs uppercase tracking-[0.3em] text-slate-500">
                  Selected parcel
                </div>
                <h2 className="mt-2 text-xl font-semibold text-slate-100">
                  {selectedParcel?.apn ?? "No parcel selected"}
                </h2>
              </div>
              {selectedParcel ? (
                <button
                  className="rounded-2xl bg-emerald-400 px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-slate-950"
                  onClick={() => router.push(`/planner/${selectedParcel.id}`)}
                >
                  Open concept plan
                </button>
              ) : null}
            </div>

            <div className="mt-5 grid gap-3 text-sm text-slate-300">
              <DetailRow label="County" value={selectedParcel?.county ?? "Click a parcel"} />
              <DetailRow label="Area" value={formatArea(selectedParcel)} />
              <DetailRow label="Address" value={selectedParcel?.address ?? "Unavailable"} />
              <DetailRow label="Owner" value={selectedParcel?.ownerName ?? "Unavailable"} />
              <DetailRow label="Source Provider" value={selectedParcel?.sourceProvider ?? "—"} />
              <DetailRow label="Dataset" value={selectedParcel?.sourceDataset ?? "—"} />
              <DetailRow label="Source Object ID" value={selectedParcel?.sourceObjectId ?? "—"} />
            </div>

            {selectedParcel ? (
              <div className="mt-5 rounded-2xl border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-400">
                This parcel has been normalized and cached. Open the planner to run frontage-aware
                loting and topology optimization on the same parcel record.
              </div>
            ) : (
              <div className="mt-5 rounded-2xl border border-dashed border-slate-700 p-4 text-sm text-slate-500">
                Search by APN or click the map to load a live parcel record.
              </div>
            )}
          </div>

          <div className="mt-4 rounded-[24px] border border-slate-800 bg-slate-900/60 p-5">
            <div className="text-xs uppercase tracking-[0.3em] text-slate-500">Next step</div>
            <p className="mt-3 text-sm text-slate-300">
              The planner uses the cached parcel geometry, not the raw county payload, so concept
              runs and saved results stay stable even if the source system changes later.
            </p>
            {selectedParcel ? (
              <Link
                href={`/planner/${selectedParcel.id}`}
                className="mt-4 inline-flex rounded-2xl border border-emerald-400/40 px-4 py-2 text-sm font-semibold text-emerald-300"
              >
                Continue to planner
              </Link>
            ) : null}
          </div>
        </aside>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-1 text-sm text-slate-200">{value}</div>
    </div>
  );
}

function formatArea(parcel: ParcelRecord | null) {
  if (!parcel) return "—";
  const sqft = parcel.areaSqft ? `${parcel.areaSqft.toLocaleString()} sqft` : "unknown";
  const acres = parcel.areaAcres ? `${parcel.areaAcres.toFixed(2)} ac` : "unknown";
  return `${sqft} • ${acres}`;
}
