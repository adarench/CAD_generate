"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { ClientMapView } from "@/components/ClientMapView";
import {
  PARCEL_VIEWPORT_MIN_ZOOM,
  parcelViewportLimitForZoom,
  useParcelViewportQuery,
} from "@/hooks/useParcelViewportQuery";
import { fetchParcelByClick, fetchRecentParcels, searchParcelByApn } from "@/lib/api";
import { COUNTY_DEFAULT_VIEWS, DEFAULT_MAP_COUNTY, DEFAULT_MAP_VIEW } from "@/lib/mapConfig";
import { PARCEL_DEBUG_ENABLED } from "@/lib/parcelDebug";
import type { ParcelRecord } from "@/lib/parcels";
import { SUPPORTED_UTAH_COUNTIES } from "@/services/parcels/arcgisParcelClient";

const counties = [...SUPPORTED_UTAH_COUNTIES];

export default function MapPage() {
  const recentParcels = useQuery({
    queryKey: ["recent-parcels-map"],
    queryFn: () => fetchRecentParcels(6),
  });
  const [selectedParcel, setSelectedParcel] = useState<ParcelRecord | null>(null);
  const [candidateParcels, setCandidateParcels] = useState<ParcelRecord[]>([]);
  const [apnQuery, setApnQuery] = useState("");
  const [county, setCounty] = useState<string>(DEFAULT_MAP_COUNTY);
  const [hoveredParcelId, setHoveredParcelId] = useState<string | null>(null);
  const [viewport, setViewport] = useState<{
    minLng: number;
    minLat: number;
    maxLng: number;
    maxLat: number;
    zoom: number;
  } | null>(null);
  const [mapView, setMapView] = useState(COUNTY_DEFAULT_VIEWS[DEFAULT_MAP_COUNTY] ?? DEFAULT_MAP_VIEW);
  const [mapStatus, setMapStatus] = useState<{ state: "booting" | "ready" | "error"; message?: string }>({
    state: "booting",
  });
  const [showMapDebug, setShowMapDebug] = useState(false);
  const [autoLoadedSearchKey, setAutoLoadedSearchKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lookupMessage, setLookupMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const visibleParcels = useParcelViewportQuery(county, viewport);
  const parcelFeatureCount = visibleParcels.data?.length ?? 0;
  const viewportLimit = parcelViewportLimitForZoom(viewport?.zoom);

  const parcelContextGeoJSON = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (!parcelFeatureCount) {
      return null;
    }
    return {
      type: "FeatureCollection",
      features: visibleParcels.data!.map((parcel) => ({
        type: "Feature",
        properties: {
          id: parcel.id,
          apn: parcel.apn,
        },
        geometry: parcel.geometryGeoJSON,
      })),
    };
  }, [parcelFeatureCount, visibleParcels.data]);

  const parcelLayerFeatureCount = parcelContextGeoJSON?.features.length ?? 0;
  const parcelRequestState = useMemo(() => {
    if (!viewport) {
      return "waiting for viewport";
    }
    if (viewport.zoom < PARCEL_VIEWPORT_MIN_ZOOM) {
      return `zoom below parcel load threshold (${PARCEL_VIEWPORT_MIN_ZOOM})`;
    }
    if (visibleParcels.isError) {
      return "parcel request failed";
    }
    if (visibleParcels.isLoading && !parcelFeatureCount) {
      return "loading parcels";
    }
    if (visibleParcels.isFetching && parcelFeatureCount) {
      return "refreshing parcels";
    }
    if (parcelLayerFeatureCount) {
      return "parcel layer ready";
    }
    if (visibleParcels.isSuccess) {
      return "request returned 0 parcels";
    }
    return "standing by";
  }, [
    parcelFeatureCount,
    parcelLayerFeatureCount,
    viewport,
    visibleParcels.isError,
    visibleParcels.isFetching,
    visibleParcels.isLoading,
    visibleParcels.isSuccess,
  ]);
  const mapDebug = useMemo(
    () => ({
      county,
      zoom: viewport?.zoom ?? null,
      bounds: viewport
        ? `${viewport.minLng.toFixed(5)}, ${viewport.minLat.toFixed(5)} → ${viewport.maxLng.toFixed(5)}, ${viewport.maxLat.toFixed(5)}`
        : "pending",
      requestState: parcelRequestState,
      parcelFeatureCount,
      viewportLimit,
      parcelLayerFeatureCount,
      layerRendered: parcelLayerFeatureCount > 0 ? "yes" : "no",
      requestError: visibleParcels.error instanceof Error ? visibleParcels.error.message : null,
    }),
    [county, parcelFeatureCount, parcelLayerFeatureCount, parcelRequestState, viewport, viewportLimit, visibleParcels.error]
  );

  useEffect(() => {
    if (!viewport) return;
    if (PARCEL_DEBUG_ENABLED) {
      console.log("[parcel-map] viewport", {
        county,
        viewport,
      });
    }
  }, [county, viewport]);

  useEffect(() => {
    if (!visibleParcels.data) return;
    if (PARCEL_DEBUG_ENABLED) {
      console.log("[parcel-map] visible parcels", {
        county,
        count: visibleParcels.data.length,
      });
    }
  }, [county, visibleParcels.data]);

  useEffect(() => {
    if (!selectedParcel) return;
    setMapView({
      lng: selectedParcel.centroid.lng,
      lat: selectedParcel.centroid.lat,
      zoom: 16.2,
    });
  }, [selectedParcel]);

  async function runApnSearch(targetCounty: string, targetApn: string) {
    setLoading(true);
    setError(null);
    setLookupMessage(null);
    try {
      const matches = await searchParcelByApn(targetCounty, targetApn);
      setSelectedParcel(matches[0] ?? null);
      setCandidateParcels(matches);
      setCounty(targetCounty);
      setApnQuery(targetApn);
      if (matches[0]) {
        setMapView({
          lng: matches[0].centroid.lng,
          lat: matches[0].centroid.lat,
          zoom: 16.2,
        });
      }
      if (matches.length > 1) {
        setLookupMessage("Multiple parcels matched that APN. Review the candidate list and open the right parcel in Studio.");
      } else if (matches.length === 1) {
        setLookupMessage("Discovery located a normalized parcel record and framed it for Studio launch.");
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

  async function handleApnSearch() {
    await runApnSearch(county, apnQuery);
  }

  async function handleMapClick(lat: number, lng: number) {
    setLoading(true);
    setError(null);
    setLookupMessage(null);
    try {
      const response = await fetchParcelByClick(lng, lat, county);
      setSelectedParcel(response.selected);
      setCandidateParcels(response.candidates);
      setLookupMessage(response.message ?? "Parcel selected from the GIS surface.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Parcel lookup failed.");
      setCandidateParcels([]);
    } finally {
      setLoading(false);
    }
  }

  function handleCountyChange(nextCounty: string) {
    setCounty(nextCounty);
    setSelectedParcel(null);
    setCandidateParcels([]);
    setHoveredParcelId(null);
    setLookupMessage(`Switched to ${nextCounty} County. Zoom in to inspect parcel boundaries and launch Studio.`);
    setError(null);
    setMapView(COUNTY_DEFAULT_VIEWS[nextCounty] ?? DEFAULT_MAP_VIEW);
  }

  function handleVisibleParcelClick(parcelId: string) {
    const clicked = visibleParcels.data?.find((parcel) => parcel.id === parcelId);
    if (!clicked) return;
    setSelectedParcel(clicked);
    setCandidateParcels([clicked]);
    setLookupMessage("Parcel selected directly from the live GIS layer.");
    setError(null);
  }

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const apnFromUrl = params.get("apn")?.trim();
    const countyFromUrl = normalizeCountyParam(params.get("county"));
    if (!apnFromUrl) return;
    const targetCounty = countyFromUrl || county;
    const searchKey = `${targetCounty}:${apnFromUrl}`;
    if (autoLoadedSearchKey === searchKey) return;
    setAutoLoadedSearchKey(searchKey);
    void runApnSearch(targetCounty, apnFromUrl);
  }, [autoLoadedSearchKey, county]);

  return (
    <div className="flex min-h-[calc(100vh-72px)] flex-col bg-slate-950">
      <div className="border-b border-slate-800 bg-slate-950/90 px-5 py-4">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-5">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.32em] text-cyan-300">
              GIS discovery layer
            </div>
            <h1 className="mt-2 text-2xl font-semibold text-slate-100">
              Browse real parcels, inspect context, and launch Studio
            </h1>
          </div>
          <div className="flex min-w-[620px] flex-wrap items-center gap-3 rounded-[24px] border border-slate-800 bg-slate-900/80 p-3">
            <select
              className="rounded-2xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              value={county}
              onChange={(event) => handleCountyChange(event.target.value)}
            >
              {counties.map((entry) => (
                <option key={entry} value={entry}>
                  {entry} County
                </option>
              ))}
            </select>
            <input
              className="flex-1 rounded-2xl border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100"
              placeholder="Search county + APN"
              value={apnQuery}
              onChange={(event) => setApnQuery(event.target.value)}
            />
            <button
              className="rounded-2xl bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50"
              onClick={handleApnSearch}
              disabled={loading || !apnQuery.trim()}
            >
              {loading ? "Locating..." : "Find parcel"}
            </button>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[300px_minmax(0,1fr)_400px]">
        <aside className="border-r border-slate-800 bg-slate-950/88 p-5 xl:overflow-y-auto">
          <DiscoveryPanel title="Workflow" eyebrow="Locate → inspect → launch">
            <div className="space-y-3 text-sm leading-7 text-slate-300">
              <p>1. Stay on the GIS surface to inspect real parcel geometry in place.</p>
              <p>2. Search by county + APN or click a visible parcel boundary.</p>
              <p>3. Review the normalized record, then open the parcel in Studio.</p>
            </div>
          </DiscoveryPanel>

          <DiscoveryPanel title="Recent parcels" eyebrow="Ready for Studio">
            <div className="space-y-3">
              {(recentParcels.data ?? []).map((parcel) => (
                <button
                  key={parcel.id}
                  className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-left transition hover:border-slate-600"
                  onClick={() => {
                    setSelectedParcel(parcel);
                    setCandidateParcels([parcel]);
                    setLookupMessage("Loaded from recent parcel history.");
                    setMapView({
                      lng: parcel.centroid.lng,
                      lat: parcel.centroid.lat,
                      zoom: 16.1,
                    });
                  }}
                >
                  <div className="font-semibold text-slate-100">{parcel.apn ?? parcel.id}</div>
                  <div className="mt-1 text-sm text-slate-400">
                    {parcel.county} County • {parcel.areaAcres?.toFixed(2) ?? "—"} acres
                  </div>
                </button>
              ))}
              {!recentParcels.data?.length ? (
                <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-6 text-sm text-slate-500">
                  Recent normalized parcels will appear here after live discovery.
                </div>
              ) : null}
            </div>
          </DiscoveryPanel>

          <DiscoveryPanel title="Candidate parcels" eyebrow="Search and click results">
            <div className="space-y-3">
              {candidateParcels.length ? (
                candidateParcels.map((parcel) => {
                  const active = parcel.id === selectedParcel?.id;
                  return (
                    <button
                      key={parcel.id}
                      className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                        active
                          ? "border-cyan-400/50 bg-cyan-400/10"
                          : "border-slate-800 bg-slate-950/70 hover:border-slate-600"
                      }`}
                      onClick={() => setSelectedParcel(parcel)}
                    >
                      <div className="font-semibold text-slate-100">{parcel.apn ?? parcel.id}</div>
                      <div className="mt-1 text-sm text-slate-400">{parcel.address ?? "Address unavailable"}</div>
                      <div className="mt-1 text-xs uppercase tracking-[0.22em] text-slate-500">
                        {parcel.areaAcres?.toFixed(2) ?? "—"} acres
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-6 text-sm text-slate-500">
                  Candidate parcels appear here after APN searches and map selections.
                </div>
              )}
            </div>
          </DiscoveryPanel>

          {lookupMessage ? (
            <div className="mt-4 rounded-2xl border border-cyan-400/30 bg-cyan-400/10 p-4 text-sm text-cyan-100">
              {lookupMessage}
            </div>
          ) : null}

          {error ? (
            <div className="mt-4 rounded-2xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
              {error}
            </div>
          ) : null}
        </aside>

        <section className="relative min-h-[720px] overflow-hidden bg-slate-950">
          <ClientMapView
            onParcelClick={handleMapClick}
            onVisibleParcelClick={handleVisibleParcelClick}
            onParcelHover={setHoveredParcelId}
            onViewportIdle={setViewport}
            parcelGeometry={selectedParcel?.geometryGeoJSON ?? null}
            contextGeoJSON={parcelContextGeoJSON}
            center={selectedParcel?.centroid ?? null}
            viewState={mapView}
            hoveredParcelId={hoveredParcelId}
            selectedParcelId={selectedParcel?.id ?? null}
            selectedParcelApn={selectedParcel?.apn ?? null}
            basemapMode="gis"
            visualMode="discovery"
            onMapStatusChange={setMapStatus}
          />

          <div className="absolute left-5 top-5 z-[450] rounded-full border border-slate-800 bg-slate-950/85 px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-slate-300">
            {loading ? "Querying parcel source..." : `${county} County active`}
          </div>
          <div className="absolute left-5 top-20 z-[450] rounded-[22px] border border-slate-900 bg-slate-950/96 px-4 py-3 text-xs uppercase tracking-[0.22em] text-slate-100 shadow-xl shadow-slate-950/60">
            {mapStatus.state === "ready" ? "GIS ready" : "Loading GIS"} • Zoom {viewport?.zoom?.toFixed(1) ?? "—"} •{" "}
            {parcelFeatureCount} parcels visible
          </div>
          <div className="absolute right-5 top-5 z-[450] flex items-start gap-3">
            {mapDebug.requestError ? (
              <div className="max-w-xs rounded-[20px] border border-red-500/40 bg-red-500/12 px-4 py-3 text-xs text-red-100 shadow-xl shadow-slate-950/50">
                Parcel source error: {mapDebug.requestError}
              </div>
            ) : null}
            {PARCEL_DEBUG_ENABLED ? (
              <div className="rounded-[20px] border border-slate-800 bg-slate-950/90 shadow-xl shadow-slate-950/50">
                <button
                  className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-300"
                  onClick={() => setShowMapDebug((current) => !current)}
                >
                  {showMapDebug ? "Hide debug" : "Show debug"}
                </button>
                {showMapDebug ? (
                  <div className="grid min-w-[320px] grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-2 border-t border-slate-800 px-4 py-4 text-xs text-slate-300">
                    <span className="text-slate-500">County</span>
                    <span>{mapDebug.county}</span>
                    <span className="text-slate-500">Viewport</span>
                    <span>{mapDebug.bounds}</span>
                    <span className="text-slate-500">Zoom</span>
                    <span>{mapDebug.zoom?.toFixed(1) ?? "—"}</span>
                    <span className="text-slate-500">Request</span>
                    <span>{mapDebug.requestState}</span>
                    <span className="text-slate-500">Features</span>
                    <span>{mapDebug.parcelFeatureCount}</span>
                    <span className="text-slate-500">Layer ready</span>
                    <span>{mapDebug.layerRendered}</span>
                    <span className="text-slate-500">Layer count</span>
                    <span>{mapDebug.parcelLayerFeatureCount}</span>
                    <span className="text-slate-500">Error</span>
                    <span className={mapDebug.requestError ? "text-red-300" : "text-slate-500"}>
                      {mapDebug.requestError ?? "none"}
                    </span>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          <div className="absolute bottom-5 left-5 z-[450] max-w-md rounded-[24px] border border-slate-800 bg-slate-950/92 px-5 py-4 shadow-2xl shadow-slate-950/60">
            <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-300">
              Discovery intent
            </div>
            <p className="mt-2 text-sm leading-7 text-slate-300">
              This surface is for parcel discovery and intake. Select a parcel here, then move into Studio
              for concept generation and feasibility design.
            </p>
          </div>
        </section>

        <aside className="border-l border-slate-800 bg-slate-950/94 p-5 xl:overflow-y-auto">
          <DiscoveryPanel title={selectedParcel?.apn ?? "No parcel selected"} eyebrow="Parcel drawer">
            <p className="text-sm leading-7 text-slate-300">
              {selectedParcel
                ? "Review the normalized parcel record, then launch the design workspace in a new tab."
                : "Click a visible parcel boundary or search by APN to open the parcel drawer."}
            </p>

            {selectedParcel ? (
              <Link
                href={`/studio/${selectedParcel.id}`}
                target="_blank"
                rel="noreferrer"
                className="mt-5 inline-flex w-full items-center justify-center rounded-[24px] bg-cyan-400 px-5 py-4 text-sm font-semibold uppercase tracking-[0.24em] text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300"
              >
                Open in Studio
              </Link>
            ) : null}

            <div className="mt-5 grid gap-3 text-sm text-slate-300">
              <DetailRow label="County" value={selectedParcel?.county ?? "Select a parcel"} />
              <DetailRow label="Area" value={formatArea(selectedParcel)} />
              <DetailRow label="Address" value={selectedParcel?.address ?? "Unavailable"} />
              <DetailRow label="Owner" value={selectedParcel?.ownerName ?? "Unavailable"} />
              <DetailRow label="Source provider" value={selectedParcel?.sourceProvider ?? "—"} />
              <DetailRow label="Dataset" value={selectedParcel?.sourceDataset ?? "—"} />
              <DetailRow label="Source object ID" value={selectedParcel?.sourceObjectId ?? "—"} />
              <DetailRow label="Zoning" value={selectedParcel?.zoningCode ?? "Enrichment pending"} />
            </div>
          </DiscoveryPanel>

          <DiscoveryPanel title="Studio handoff" eyebrow="Normalized parcel ID">
            <p className="text-sm leading-7 text-slate-300">
              Studio loads the cached normalized parcel record directly by ID. The design environment starts
              with the parcel boundary already framed and ready for prompt-first concept generation.
            </p>
          </DiscoveryPanel>
        </aside>
      </div>
    </div>
  );
}

function normalizeCountyParam(value: string | null) {
  if (!value) return null;
  return value.replace(/\s+County$/i, "").trim();
}

function DiscoveryPanel({
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
  const sqft = parcel.areaSqft ? `${Math.round(parcel.areaSqft).toLocaleString()} sqft` : null;
  const acres = parcel.areaAcres ? `${parcel.areaAcres.toFixed(2)} ac` : null;
  return [acres, sqft].filter(Boolean).join(" • ") || "—";
}
