"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { ClientMapView } from "@/components/ClientMapView";
import {
  PARCEL_VIEWPORT_MIN_ZOOM,
  parcelViewportLimitForZoom,
  useParcelViewportQuery,
} from "@/hooks/useParcelViewportQuery";
import { fetchParcelByClick, fetchRecentParcels, fetchRun, fetchRuns, searchParcelByApn } from "@/lib/api";
import { COUNTY_DEFAULT_VIEWS, DEFAULT_MAP_COUNTY, DEFAULT_MAP_VIEW } from "@/lib/mapConfig";
import { PARCEL_DEBUG_ENABLED } from "@/lib/parcelDebug";
import type { ParcelRecord, PipelineRun } from "@/lib/parcels";
import { useShortlist } from "@/lib/shortlist";
import { SUPPORTED_UTAH_COUNTIES } from "@/services/parcels/arcgisParcelClient";

const counties = [...SUPPORTED_UTAH_COUNTIES];

export default function MapPage() {
  const recentParcels = useQuery({
    queryKey: ["recent-parcels-map"],
    queryFn: () => fetchRecentParcels(6),
  });
  const recentRunSummaries = useQuery({
    queryKey: ["map-recent-runs"],
    queryFn: () => fetchRuns({ limit: 120, sort: "timestamp", order: "desc" }),
    staleTime: 30_000,
  });
  const shortlist = useShortlist();
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
  const [apnSearching, setApnSearching] = useState(false);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const selectionAbortRef = useRef<AbortController | null>(null);
  const selectionRequestIdRef = useRef(0);
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

  const latestRunSummaryForSelectedParcel = useMemo(() => {
    if (!selectedParcel) return null;
    return (recentRunSummaries.data ?? []).find((run) => run.parcel_id === selectedParcel.id) ?? null;
  }, [recentRunSummaries.data, selectedParcel]);

  const selectedParcelRunQuery = useQuery({
    queryKey: ["map-selected-run", latestRunSummaryForSelectedParcel?.run_id],
    queryFn: () => fetchRun(latestRunSummaryForSelectedParcel!.run_id),
    enabled: Boolean(latestRunSummaryForSelectedParcel?.run_id),
    staleTime: 30_000,
    retry: false,
  });

  const triagePreview = useMemo(
    () => buildTriagePreview(selectedParcel, selectedParcelRunQuery.data ?? null),
    [selectedParcel, selectedParcelRunQuery.data]
  );

  function abortSelectionRequest() {
    selectionAbortRef.current?.abort();
    selectionAbortRef.current = null;
  }

  function beginSelectionRequest() {
    abortSelectionRequest();
    const controller = new AbortController();
    selectionAbortRef.current = controller;
    const requestId = selectionRequestIdRef.current + 1;
    selectionRequestIdRef.current = requestId;
    return { controller, requestId };
  }

  async function runApnSearch(targetCounty: string, targetApn: string) {
    const { controller, requestId } = beginSelectionRequest();
    setApnSearching(true);
    setDrawerLoading(true);
    setError(null);
    setLookupMessage(null);
    try {
      const matches = await searchParcelByApn(targetCounty, targetApn, { signal: controller.signal });
      if (selectionRequestIdRef.current !== requestId) return;
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
        setLookupMessage("Multiple parcels matched that APN. Review the candidate list and add the right parcel to your shortlist.");
      } else if (matches.length === 1) {
        setLookupMessage("Discovery located a normalized parcel record. Add it to your shortlist to evaluate it in opportunities.");
      }
      if (!matches.length) {
        setError("No parcel found for that county/APN combination.");
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Parcel search failed.");
      setCandidateParcels([]);
    } finally {
      if (selectionRequestIdRef.current === requestId) {
        setApnSearching(false);
        setDrawerLoading(false);
      }
    }
  }

  async function handleApnSearch() {
    await runApnSearch(county, apnQuery);
  }

  async function handleMapClick(lat: number, lng: number) {
    const { controller, requestId } = beginSelectionRequest();
    setDrawerLoading(true);
    setError(null);
    setLookupMessage(null);
    try {
      const response = await fetchParcelByClick(lng, lat, county, { signal: controller.signal });
      if (selectionRequestIdRef.current !== requestId) return;
      setSelectedParcel(response.selected);
      setCandidateParcels(response.candidates);
      setLookupMessage(response.message ?? "Parcel selected from the GIS surface.");
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Parcel lookup failed.");
      setCandidateParcels([]);
    } finally {
      if (selectionRequestIdRef.current === requestId) {
        setDrawerLoading(false);
      }
    }
  }

  function handleCountyChange(nextCounty: string) {
    abortSelectionRequest();
    setCounty(nextCounty);
    setSelectedParcel(null);
    setCandidateParcels([]);
    setHoveredParcelId(null);
    setLookupMessage(`Switched to ${nextCounty} County. Zoom in to inspect parcel boundaries and shortlist candidates.`);
    setError(null);
    setApnSearching(false);
    setDrawerLoading(false);
    setMapView(COUNTY_DEFAULT_VIEWS[nextCounty] ?? DEFAULT_MAP_VIEW);
  }

  function handleVisibleParcelClick(parcelId: string) {
    const clicked = visibleParcels.data?.find((parcel) => parcel.id === parcelId);
    if (!clicked) return;
    abortSelectionRequest();
    setSelectedParcel(clicked);
    setCandidateParcels([clicked]);
    setLookupMessage("Parcel selected directly from the live GIS layer.");
    setError(null);
    setDrawerLoading(false);
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
              Browse real parcels, inspect context, and build a shortlist
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
              disabled={apnSearching || !apnQuery.trim()}
            >
              {apnSearching ? "Locating..." : "Find parcel"}
            </button>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[300px_minmax(0,1fr)_400px]">
        <aside className="border-r border-slate-800 bg-slate-950/88 p-5 xl:overflow-y-auto">
          <DiscoveryPanel title="Workflow" eyebrow="Locate → shortlist → evaluate">
            <div className="space-y-3 text-sm leading-7 text-slate-300">
              <p>1. Stay on the GIS surface to inspect real parcel geometry in place.</p>
              <p>2. Search by county + APN or click a visible parcel boundary.</p>
              <p>3. Add viable parcels to the shortlist, then move into Opportunities to compare and inspect them.</p>
            </div>
          </DiscoveryPanel>

          <DiscoveryPanel title="Shortlist" eyebrow="Selected candidates">
            <div className="space-y-4">
              <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/8 px-4 py-3 text-sm text-emerald-100">
                {shortlist.shortlistIds.length} parcels shortlisted
              </div>
              <Link
                href="/opportunities"
                className="inline-flex w-full items-center justify-center rounded-[20px] border border-emerald-400/30 bg-emerald-400/10 px-4 py-3 text-sm font-semibold uppercase tracking-[0.2em] text-emerald-200"
              >
                Open opportunities
              </Link>
              {shortlist.shortlistIds.length ? (
                <button
                  className="w-full rounded-[20px] border border-slate-700 px-4 py-3 text-sm font-semibold text-slate-200"
                  onClick={() => shortlist.clearShortlist()}
                >
                  Clear shortlist
                </button>
              ) : null}
            </div>
          </DiscoveryPanel>

          <DiscoveryPanel title="Live parcel layer" eyebrow="Real GIS only">
            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4 text-sm leading-7 text-slate-300">
                This surface shows only live parcel geometry returned from county GIS services. No synthetic parcels, opportunity scores, or demo overlays are used here.
              </div>
              <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/8 px-4 py-3 text-sm text-cyan-100">
                {parcelFeatureCount} real parcels in the current viewport
              </div>
            </div>
          </DiscoveryPanel>

          <DiscoveryPanel title="Recent parcels" eyebrow="Recent discovery">
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
            resultGeoJSON={null}
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
            {apnSearching ? "Searching APN..." : `${county} County active`}
          </div>
          <div className="absolute left-5 top-20 z-[450] rounded-[22px] border border-slate-900 bg-slate-950/96 px-4 py-3 text-xs uppercase tracking-[0.22em] text-slate-100 shadow-xl shadow-slate-950/60">
            {mapStatus.state === "ready" ? "GIS ready" : "Loading GIS"} • Zoom {viewport?.zoom?.toFixed(1) ?? "—"} •{" "}
            {parcelFeatureCount} parcels visible
          </div>
          <div className="absolute left-5 top-36 z-[450] rounded-[22px] border border-cyan-400/20 bg-slate-950/96 px-4 py-3 text-xs uppercase tracking-[0.22em] text-cyan-100 shadow-xl shadow-slate-950/60">
            {parcelFeatureCount} real parcels loaded
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
              This surface is for parcel discovery and intake. Build a shortlist here, compare opportunities,
              then inspect the winners in the parcel decision view.
            </p>
          </div>
        </section>

        <aside className="border-l border-slate-800 bg-slate-950/94 p-5 xl:overflow-y-auto">
          <DiscoveryPanel title={selectedParcel?.apn ?? "No parcel selected"} eyebrow="Parcel drawer">
            <p className="text-sm leading-7 text-slate-300">
              {selectedParcel
                ? "Review the normalized parcel record, then add it to the shortlist for comparison and later inspection."
                : "Click a visible parcel boundary or search by APN to open the parcel drawer."}
            </p>

            {selectedParcel ? (
              <div className="mt-5 rounded-[24px] border border-slate-800 bg-slate-950/70 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
                      Early triage
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <TriageBadge tone={triagePreview.tone}>{triagePreview.label}</TriageBadge>
                      {selectedParcelRunQuery.data ? (
                        <span className="rounded-full border border-slate-700 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-300">
                          {selectedParcelRunQuery.data.status.replace(/_/g, " ")}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  {drawerLoading ? (
                    <span className="text-xs uppercase tracking-[0.18em] text-cyan-300">Updating preview…</span>
                  ) : null}
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-300">{triagePreview.summary}</p>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <DetailRow label="Jurisdiction" value={selectedParcel.county} />
                  <DetailRow label="Area" value={formatArea(selectedParcel)} />
                  <DetailRow label="Zoning status" value={selectedParcel.zoningCode ?? "Not yet attached"} />
                  <DetailRow
                    label="Last run"
                    value={
                      latestRunSummaryForSelectedParcel
                        ? formatTimestamp(latestRunSummaryForSelectedParcel.timestamp)
                        : "No prior run"
                    }
                  />
                </div>
              </div>
            ) : null}

            {selectedParcel ? (
              <div className="mt-5 flex flex-col gap-3">
                <button
                  onClick={() => shortlist.toggleShortlist(selectedParcel.id)}
                  className="inline-flex w-full items-center justify-center rounded-[24px] bg-cyan-400 px-5 py-4 text-sm font-semibold uppercase tracking-[0.24em] text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300"
                >
                  {shortlist.isShortlisted(selectedParcel.id) ? "Remove from shortlist" : "Add to shortlist"}
                </button>
                <Link
                  href={`/studio/${selectedParcel.id}`}
                  className="inline-flex w-full items-center justify-center rounded-[24px] border border-slate-700 px-5 py-4 text-sm font-semibold uppercase tracking-[0.24em] text-slate-200 transition hover:border-slate-500"
                >
                  Open full decision view
                </Link>
              </div>
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

          <DiscoveryPanel title="Product flow" eyebrow="Shortlist first">
            <p className="text-sm leading-7 text-slate-300">
              Discovery feeds shortlist creation. Opportunities is the comparison and ranking surface. The
              parcel decision view is the inspection surface after comparison narrows the field.
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

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function buildTriagePreview(parcel: ParcelRecord | null, run: PipelineRun | null) {
  if (!parcel) {
    return {
      label: "Needs review",
      tone: "neutral" as const,
      summary: "Select a parcel to see a lightweight intake signal before deeper evaluation.",
    };
  }

  const roi = run?.feasibility_result?.ROI_base ?? run?.feasibility_result?.ROI ?? null;
  const confidence =
    run?.feasibility_result?.confidence_score ?? run?.feasibility_result?.confidence ?? null;

  if (!run) {
    return {
      label: "Needs review",
      tone: "neutral" as const,
      summary: "No prior pipeline run exists for this parcel yet. Use shortlist for later comparison or open the full decision view when you want deeper analysis.",
    };
  }

  if (run.status === "near_feasible") {
    return {
      label: "Conditional",
      tone: "warning" as const,
      summary: run.near_feasible_result?.reason_category
        ? `Prior run was near feasible. The main blocker was ${run.near_feasible_result.reason_category.replace(/_/g, " ")}.`
        : "Prior run was near feasible and may warrant follow-up if the constraint can be resolved.",
    };
  }

  if (run.status === "failed") {
    return {
      label: "Likely no-go",
      tone: "danger" as const,
      summary: "The latest saved run failed to produce a decision-grade result for this parcel.",
    };
  }

  if (typeof roi === "number" && roi > 0 && typeof confidence === "number" && confidence >= 0.6) {
    return {
      label: "Likely candidate",
      tone: "success" as const,
      summary: `Latest saved run completed with positive economics at ${Math.round(confidence * 100)}% confidence.`,
    };
  }

  if (typeof roi === "number" && roi <= 0) {
    return {
      label: "Likely no-go",
      tone: "danger" as const,
      summary: "Latest saved run completed, but current economics are negative under the stored assumptions.",
    };
  }

  return {
    label: "Needs review",
    tone: "neutral" as const,
    summary: "A prior run exists, but the parcel still needs deeper review before a reliable acquisition call.",
  };
}

function TriageBadge({
  tone,
  children,
}: {
  tone: "success" | "warning" | "danger" | "neutral";
  children: string;
}) {
  const classes =
    tone === "success"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
      : tone === "warning"
        ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
        : tone === "danger"
          ? "border-rose-400/40 bg-rose-400/10 text-rose-300"
          : "border-slate-700 bg-slate-900 text-slate-300";
  return (
    <span className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${classes}`}>
      {children}
    </span>
  );
}
