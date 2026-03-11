"use client";

import { useMemo } from "react";

import { ClientMapView } from "@/components/ClientMapView";
import { PlanSvgCanvas } from "@/components/studio/PlanSvgCanvas";
import type { BasemapMode } from "@/lib/mapConfig";
import type { OptimizationResponse, ParcelRecord } from "@/lib/parcels";

export const STUDIO_LAYER_OPTIONS = ["parcel", "road", "easements", "lots", "lot_labels"] as const;
export type StudioLayerKey = (typeof STUDIO_LAYER_OPTIONS)[number];

interface StudioCanvasProps {
  parcel: ParcelRecord | null | undefined;
  result: OptimizationResponse | null;
  visibleLayers: StudioLayerKey[];
  basemapMode: BasemapMode;
  resetNonce: number;
  onToggleLayer: (layer: StudioLayerKey) => void;
  onBasemapChange: (mode: BasemapMode) => void;
  onResetView: () => void;
}

export function StudioCanvas({
  parcel,
  result,
  visibleLayers,
  basemapMode,
  resetNonce,
  onToggleLayer,
  onBasemapChange,
  onResetView,
}: StudioCanvasProps) {
  const filteredResult = useMemo(() => {
    if (!result?.resultGeoJSON) return null;
    return {
      ...result.resultGeoJSON,
      features: result.resultGeoJSON.features.filter((feature) =>
        visibleLayers.includes(String(feature.properties?.layer) as StudioLayerKey)
      ),
    };
  }, [result, visibleLayers]);

  const canvasKey = `${parcel?.id ?? "studio"}-${resetNonce}`;
  const showPlanCanvas = basemapMode === "drawing";

  return (
    <div className="relative flex-1 overflow-hidden bg-[#dde4e8]">
      {showPlanCanvas ? (
        <PlanSvgCanvas
          key={canvasKey}
          parcel={parcel}
          result={result}
          visibleLayers={visibleLayers}
          resetNonce={resetNonce}
        />
      ) : (
        <>
          <div className="studio-grid-overlay pointer-events-none absolute inset-0 z-[120]" />
          <ClientMapView
            key={canvasKey}
            parcelGeometry={parcel?.geometryGeoJSON ?? null}
            center={parcel?.centroid ?? null}
            resultGeoJSON={filteredResult}
            basemapMode={basemapMode}
            visualMode="studio"
          />
        </>
      )}

      <div className="absolute left-5 top-5 z-[450] flex flex-wrap items-center gap-3 rounded-[24px] border border-slate-400/40 bg-white/92 px-4 py-3 shadow-xl shadow-slate-500/10 backdrop-blur">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.26em] text-slate-500">
            Basemap
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {(["drawing", "gis", "aerial"] as BasemapMode[]).map((mode) => {
              const active = basemapMode === mode;
              return (
                <button
                  key={mode}
                  className={`rounded-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] transition ${
                    active
                      ? "bg-slate-950 text-slate-50"
                      : "border border-slate-300 bg-white text-slate-600 hover:border-slate-500"
                  }`}
                  onClick={() => onBasemapChange(mode)}
                >
                  {mode === "drawing" ? "None / Drawing" : mode}
                </button>
              );
            })}
          </div>
        </div>

        <div className="h-12 w-px bg-slate-200" />

        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.26em] text-slate-500">
            Layers
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {STUDIO_LAYER_OPTIONS.map((layer) => {
              const active = visibleLayers.includes(layer);
              return (
                <button
                  key={layer}
                  className={`rounded-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] transition ${
                    active
                      ? "bg-cyan-500 text-slate-950"
                      : "border border-slate-300 bg-white text-slate-600 hover:border-slate-500"
                  }`}
                  onClick={() => onToggleLayer(layer)}
                >
                  {layer.replace("_", " ")}
                </button>
              );
            })}
          </div>
        </div>

        <div className="h-12 w-px bg-slate-200" />

        <button
          className="rounded-full border border-slate-300 bg-white px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-700 transition hover:border-slate-500"
          onClick={onResetView}
        >
          Reset View
        </button>
      </div>

      <div className="absolute bottom-5 left-5 z-[450] rounded-[24px] border border-slate-300/80 bg-white/90 px-4 py-3 shadow-xl shadow-slate-500/10 backdrop-blur">
        <div className="text-[10px] font-semibold uppercase tracking-[0.26em] text-slate-500">
          Canvas mode
        </div>
        <div className="mt-2 text-sm text-slate-700">
          {basemapMode === "drawing"
            ? "Parcel-first concept canvas"
            : basemapMode === "aerial"
              ? "Aerial context enabled"
              : "GIS context enabled"}
        </div>
      </div>
    </div>
  );
}
