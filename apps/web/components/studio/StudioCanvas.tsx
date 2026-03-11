"use client";

import { useMemo, useState } from "react";

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
  const [showLayerMenu, setShowLayerMenu] = useState(false);
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

      <div className="absolute left-1/2 top-5 z-[450] flex max-w-[min(760px,calc(100%-10rem))] -translate-x-1/2 flex-wrap items-center justify-center gap-2 rounded-full border border-slate-300/80 bg-white/90 px-3 py-2 shadow-lg shadow-slate-500/10 backdrop-blur">
        <div className="hidden text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500 lg:block">
          Canvas
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(["drawing", "gis", "aerial"] as BasemapMode[]).map((mode) => {
            const active = basemapMode === mode;
            return (
              <button
                key={mode}
                className={`rounded-full px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] transition ${
                  active
                    ? "bg-slate-950 text-slate-50"
                    : "border border-slate-300 bg-white text-slate-600 hover:border-slate-500"
                }`}
                onClick={() => onBasemapChange(mode)}
              >
                {mode === "drawing" ? "Drawing" : mode}
              </button>
            );
          })}
        </div>
        <button
          className={`rounded-full px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] transition ${
            showLayerMenu
              ? "bg-cyan-500 text-slate-950"
              : "border border-slate-300 bg-white text-slate-600 hover:border-slate-500"
          }`}
          onClick={() => setShowLayerMenu((current) => !current)}
        >
          Layers
        </button>
        <button
          className="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-700 transition hover:border-slate-500"
          onClick={onResetView}
        >
          Reset
        </button>
      </div>

      {showLayerMenu ? (
        <div className="absolute left-1/2 top-[4.35rem] z-[450] w-[min(360px,calc(100%-2rem))] -translate-x-1/2 rounded-[20px] border border-slate-300/90 bg-white/95 p-3 shadow-xl shadow-slate-500/10 backdrop-blur">
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
            Visible layers
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {STUDIO_LAYER_OPTIONS.map((layer) => {
              const active = visibleLayers.includes(layer);
              return (
                <button
                  key={layer}
                  className={`rounded-full px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] transition ${
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
      ) : null}

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
