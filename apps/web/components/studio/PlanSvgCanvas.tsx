"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { OptimizationResponse, ParcelRecord } from "@/lib/parcels";
import {
  boundsForPlanFeatures,
  featurePathData,
  flipY,
  padBounds,
  projectParcelGeometry,
  projectResultGeometry,
  type PlanBounds,
} from "@/lib/studioPlan";

type StudioLayerKey = "parcel" | "road" | "easements" | "lots" | "lot_labels";

interface PlanSvgCanvasProps {
  parcel: ParcelRecord | null | undefined;
  result: OptimizationResponse | null;
  visibleLayers: StudioLayerKey[];
  resetNonce: number;
}

const DEFAULT_VIEW: PlanBounds = {
  minX: -120,
  minY: -120,
  maxX: 120,
  maxY: 120,
  width: 240,
  height: 240,
};

export function PlanSvgCanvas({ parcel, result, visibleLayers, resetNonce }: PlanSvgCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const dragStateRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    startBounds: PlanBounds;
  } | null>(null);
  const [viewportAspect, setViewportAspect] = useState(1);
  const [isPanning, setIsPanning] = useState(false);
  const parcelFeatures = useMemo(() => {
    if (!visibleLayers.includes("parcel")) return [];
    return projectParcelGeometry(parcel);
  }, [parcel, visibleLayers]);
  const resultFeatures = useMemo(
    () => projectResultGeometry(parcel, result, visibleLayers),
    [parcel, result, visibleLayers]
  );
  const combinedFeatures = useMemo(() => {
    const hasResultParcel = resultFeatures.some((feature) => feature.layer === "parcel");
    return hasResultParcel ? resultFeatures : [...parcelFeatures, ...resultFeatures];
  }, [parcelFeatures, resultFeatures]);
  const parcelOnlyBounds = useMemo(() => boundsForPlanFeatures(parcelFeatures), [parcelFeatures]);
  const planOnlyFeatures = useMemo(
    () => resultFeatures.filter((feature) => ["road", "lots", "easements", "lot_labels"].includes(feature.layer)),
    [resultFeatures]
  );
  const planOnlyBounds = useMemo(() => boundsForPlanFeatures(planOnlyFeatures), [planOnlyFeatures]);
  const fitBounds = useMemo(() => {
    const hasLots = planOnlyFeatures.some((feature) => feature.layer === "lots");
    const hasPlan = planOnlyFeatures.some((feature) => ["road", "lots", "easements"].includes(feature.layer));
    const bounds = hasPlan ? planOnlyBounds : boundsForPlanFeatures(combinedFeatures);
    if (!bounds) return DEFAULT_VIEW;
    const padded = padBounds(bounds, hasLots ? 0.06 : 0.08);
    return fitBoundsToViewport(padded, viewportAspect);
  }, [combinedFeatures, planOnlyBounds, planOnlyFeatures, viewportAspect]);
  const [viewBounds, setViewBounds] = useState<PlanBounds>(fitBounds);

  useEffect(() => {
    setViewBounds(fitBounds);
  }, [fitBounds, resetNonce]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const update = () => {
      const width = element.clientWidth || 1;
      const height = element.clientHeight || 1;
      setViewportAspect(width / height);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const maxDimension = Math.max(viewBounds.width, viewBounds.height);
  const hasLots = resultFeatures.some((feature) => feature.layer === "lots");
  const lotFeatures = combinedFeatures.filter((feature) => feature.layer === "lots");
  const fitLabel = hasLots ? "Fit layout" : "Fit parcel";
  const lotLabelFeatures = combinedFeatures.filter(
    (feature) => feature.layer === "lot_labels" && feature.geometry.type === "Point" && feature.text
  );
  const labelStride = Math.max(1, Math.ceil(lotLabelFeatures.length / 80));
  const detailLabelStride = Math.max(1, Math.ceil(lotLabelFeatures.length / 36));
  const parcelFillFeatures = combinedFeatures.filter((feature) => feature.layer === "parcel");
  const easementFeatures = combinedFeatures.filter((feature) => feature.layer === "easements");
  const roadFeatures = combinedFeatures.filter((feature) => feature.layer === "road");
  const parcelOutlineFeatures = parcelFillFeatures;
  const detailBounds = useMemo(() => {
    if (!hasLots || lotLabelFeatures.length < 12) return null;
    const points = lotLabelFeatures.flatMap((feature) =>
      feature.geometry.type === "Point" ? [feature.geometry.coordinates] : []
    );
    const overall = boundsForPoints(points);
    if (!overall) return null;
    const cluster = densestClusterBounds(points, overall);
    if (!cluster) return null;
    return fitBoundsToViewport(padBounds(cluster, 0.55), 1);
  }, [hasLots, lotLabelFeatures]);

  function zoom(factor: number) {
    setViewBounds((current) => zoomBounds(current, factor));
  }

  function handlePointerDown(event: React.PointerEvent<SVGSVGElement>) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    dragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startBounds: viewBounds,
    };
    setIsPanning(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const dragState = dragStateRef.current;
    const element = containerRef.current;
    if (!dragState || !element || dragState.pointerId !== event.pointerId) return;
    const width = element.clientWidth || 1;
    const height = element.clientHeight || 1;
    const dx = ((event.clientX - dragState.startX) / width) * dragState.startBounds.width;
    const dy = ((event.clientY - dragState.startY) / height) * dragState.startBounds.height;
    setViewBounds({
      minX: dragState.startBounds.minX - dx,
      maxX: dragState.startBounds.maxX - dx,
      minY: dragState.startBounds.minY + dy,
      maxY: dragState.startBounds.maxY + dy,
      width: dragState.startBounds.width,
      height: dragState.startBounds.height,
    });
  }

  function handlePointerUp(event: React.PointerEvent<SVGSVGElement>) {
    if (dragStateRef.current?.pointerId === event.pointerId) {
      dragStateRef.current = null;
      setIsPanning(false);
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return (
    <div ref={containerRef} className="relative h-full w-full bg-[#e8edef]">
      <svg
        className={`h-full w-full select-none ${isPanning ? "cursor-grabbing" : "cursor-grab"}`}
        viewBox={`${viewBounds.minX} ${viewBounds.minY} ${viewBounds.width} ${viewBounds.height}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        <defs>
          <pattern id="studio-grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#cfd8dc" strokeWidth="0.5" />
          </pattern>
          <pattern id="studio-grid-major" width="200" height="200" patternUnits="userSpaceOnUse">
            <rect width="200" height="200" fill="url(#studio-grid)" />
            <path d="M 200 0 L 0 0 0 200" fill="none" stroke="#b7c3c9" strokeWidth="1" />
          </pattern>
        </defs>

        <rect
          x={viewBounds.minX}
          y={viewBounds.minY}
          width={viewBounds.width}
          height={viewBounds.height}
          fill="#edf2f4"
        />
        <rect
          x={viewBounds.minX}
          y={viewBounds.minY}
          width={viewBounds.width}
          height={viewBounds.height}
          fill="url(#studio-grid-major)"
          opacity="0.9"
        />

        <g transform={`translate(0 ${viewBounds.minY + viewBounds.maxY}) scale(1 -1)`}>
          {parcelFillFeatures.map((feature) => {
            const path = featurePathData(feature);
            if (!path) return null;
            const style = layerStyle("parcel-fill");
            return (
              <path
                key={`${feature.id}-parcel-fill`}
                d={path}
                fill={style.fill}
                fillOpacity={style.fillOpacity}
                stroke="none"
              />
            );
          })}

          {lotFeatures.map((feature) => {
            const path = featurePathData(feature);
            if (!path) return null;
            const style = layerStyle("lots");
            return (
              <path
                key={`${feature.id}-${feature.layer}`}
                d={path}
                fill={style.fill}
                fillOpacity={style.fillOpacity}
                stroke={style.stroke}
                strokeOpacity={style.strokeOpacity}
                strokeWidth={style.strokeWidth}
                vectorEffect="non-scaling-stroke"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            );
          })}

          {easementFeatures.map((feature) => {
            const path = featurePathData(feature);
            if (!path) return null;
            const style = layerStyle("easements");
            return (
              <path
                key={`${feature.id}-${feature.layer}`}
                d={path}
                fill={style.fill}
                fillOpacity={style.fillOpacity}
                stroke={style.stroke}
                strokeOpacity={style.strokeOpacity}
                strokeWidth={style.strokeWidth}
                vectorEffect="non-scaling-stroke"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            );
          })}

          {roadFeatures.map((feature) => {
            const path = featurePathData(feature);
            if (!path) return null;
            const style = layerStyle("road");
            return (
              <path
                key={`${feature.id}-${feature.layer}`}
                d={path}
                fill={style.fill}
                fillOpacity={style.fillOpacity}
                stroke={style.stroke}
                strokeOpacity={style.strokeOpacity}
                strokeWidth={style.strokeWidth}
                vectorEffect="non-scaling-stroke"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            );
          })}

          {parcelOutlineFeatures.map((feature) => {
            const path = featurePathData(feature);
            if (!path) return null;
            const style = layerStyle("parcel-outline");
            return (
              <path
                key={`${feature.id}-parcel-outline`}
                d={path}
                fill="none"
                stroke={style.stroke}
                strokeOpacity={style.strokeOpacity}
                strokeWidth={style.strokeWidth}
                vectorEffect="non-scaling-stroke"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            );
          })}
        </g>

        {lotLabelFeatures
          .filter((_, index) => index % labelStride === 0)
          .map((feature) => {
            if (feature.geometry.type !== "Point") return null;
            return (
              <text
                key={`${feature.id}-label`}
                x={feature.geometry.coordinates[0]}
                y={flipY(feature.geometry.coordinates[1], viewBounds)}
                fontSize={labelFontSize(maxDimension)}
                fontWeight="700"
                textAnchor="middle"
                dominantBaseline="middle"
                fill="#0f172a"
                stroke="#f8fafc"
                strokeWidth="0.9"
                paintOrder="stroke"
              >
                {feature.text.replace(/^LOT_/, "")}
              </text>
            );
          })}

        {combinedFeatures
          .filter((feature) => feature.layer === "parcel" && feature.text && feature.geometry.type === "Polygon")
          .slice(0, 1)
          .map((feature) => {
            if (feature.geometry.type !== "Polygon") return null;
            const firstRing = feature.geometry.rings[0];
            const anchor = firstRing[Math.max(0, Math.floor(firstRing.length / 2) - 1)] ?? [0, 0];
            return (
              <text
                key={`${feature.id}-apn`}
                x={anchor[0]}
                y={flipY(anchor[1], viewBounds)}
                fontSize="12px"
                fontWeight="700"
                textAnchor="middle"
                dominantBaseline="ideographic"
                fill="#9a3412"
                stroke="#fff7ed"
                strokeWidth="1.6"
                paintOrder="stroke"
              >
                {feature.text}
              </text>
            );
          })}
      </svg>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-[#e8edef] via-[#e8edef]/70 to-transparent" />

      {detailBounds ? (
        <div className="absolute bottom-5 left-5 z-[460] h-[240px] w-[220px] overflow-hidden rounded-[28px] border border-slate-300/80 bg-white/95 shadow-xl shadow-slate-500/15">
          <div className="border-b border-slate-200/90 px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">
            Lot detail
          </div>
          <svg
            className="h-[calc(100%-45px)] w-full"
            viewBox={`${detailBounds.minX} ${detailBounds.minY} ${detailBounds.width} ${detailBounds.height}`}
            preserveAspectRatio="xMidYMid meet"
          >
            <rect
              x={detailBounds.minX}
              y={detailBounds.minY}
              width={detailBounds.width}
              height={detailBounds.height}
              fill="#f8fafc"
            />
            <g transform={`translate(0 ${detailBounds.minY + detailBounds.maxY}) scale(1 -1)`}>
              {lotFeatures.map((feature) => {
                const path = featurePathData(feature);
                if (!path) return null;
                const style = layerStyle("lots");
                return (
                  <path
                    key={`${feature.id}-detail-lot`}
                    d={path}
                    fill={style.fill}
                    fillOpacity={style.fillOpacity}
                    stroke={style.stroke}
                    strokeOpacity={style.strokeOpacity}
                    strokeWidth={style.strokeWidth}
                    vectorEffect="non-scaling-stroke"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                );
              })}
              {easementFeatures.map((feature) => {
                const path = featurePathData(feature);
                if (!path) return null;
                const style = layerStyle("easements");
                return (
                  <path
                    key={`${feature.id}-detail-easement`}
                    d={path}
                    fill={style.fill}
                    fillOpacity={style.fillOpacity}
                    stroke={style.stroke}
                    strokeOpacity={style.strokeOpacity}
                    strokeWidth={style.strokeWidth}
                    vectorEffect="non-scaling-stroke"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                );
              })}
              {roadFeatures.map((feature) => {
                const path = featurePathData(feature);
                if (!path) return null;
                const style = layerStyle("road");
                return (
                  <path
                    key={`${feature.id}-detail-road`}
                    d={path}
                    fill={style.fill}
                    fillOpacity={style.fillOpacity}
                    stroke={style.stroke}
                    strokeOpacity={style.strokeOpacity}
                    strokeWidth={style.strokeWidth}
                    vectorEffect="non-scaling-stroke"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                );
              })}
              {parcelOutlineFeatures.map((feature) => {
                const path = featurePathData(feature);
                if (!path) return null;
                const style = layerStyle("parcel-outline");
                return (
                  <path
                    key={`${feature.id}-detail-parcel-outline`}
                    d={path}
                    fill="none"
                    stroke={style.stroke}
                    strokeOpacity={style.strokeOpacity}
                    strokeWidth={style.strokeWidth}
                    vectorEffect="non-scaling-stroke"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                );
              })}
            </g>

            {lotLabelFeatures
              .filter((_, index) => index % detailLabelStride === 0)
              .map((feature) => {
                if (feature.geometry.type !== "Point") return null;
                return (
                  <text
                    key={`${feature.id}-detail-label`}
                    x={feature.geometry.coordinates[0]}
                    y={flipY(feature.geometry.coordinates[1], detailBounds)}
                    fontSize="11px"
                    fontWeight="700"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="#0f172a"
                    stroke="#f8fafc"
                    strokeWidth="1"
                    paintOrder="stroke"
                  >
                    {feature.text.replace(/^LOT_/, "")}
                  </text>
                );
              })}
          </svg>
        </div>
      ) : null}

      <div className="absolute right-5 top-5 z-[460] flex flex-col gap-2">
        <CanvasControl onClick={() => zoom(0.8)}>Zoom in</CanvasControl>
        <CanvasControl onClick={() => zoom(1.25)}>Zoom out</CanvasControl>
        <CanvasControl onClick={() => setViewBounds(fitBounds)}>{fitLabel}</CanvasControl>
        {hasLots && parcelOnlyBounds ? (
          <CanvasControl onClick={() => setViewBounds(fitBoundsToViewport(padBounds(parcelOnlyBounds, 0.08), viewportAspect))}>
            Overview parcel
          </CanvasControl>
        ) : null}
        {hasLots && planOnlyBounds ? (
          <CanvasControl onClick={() => setViewBounds(fitBoundsToViewport(padBounds(planOnlyBounds, 0.06), viewportAspect))}>
            Focus lots
          </CanvasControl>
        ) : null}
      </div>

      <div className="absolute bottom-5 right-5 z-[460] rounded-[20px] border border-slate-300/90 bg-white/94 px-4 py-3 text-xs uppercase tracking-[0.22em] text-slate-600 shadow-xl shadow-slate-500/10">
        {isPanning ? "Panning canvas" : hasLots ? "Drag to pan • engine layout rendered" : "Drag to pan • parcel geometry rendered"}
      </div>
    </div>
  );
}

function CanvasControl({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      className="rounded-full border border-slate-300 bg-white/95 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-700 shadow-lg shadow-slate-500/10 transition hover:border-slate-500"
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function zoomBounds(bounds: PlanBounds, factor: number): PlanBounds {
  const centerX = bounds.minX + bounds.width / 2;
  const centerY = bounds.minY + bounds.height / 2;
  const width = Math.max(bounds.width * factor, 30);
  const height = Math.max(bounds.height * factor, 30);
  return {
    minX: centerX - width / 2,
    minY: centerY - height / 2,
    maxX: centerX + width / 2,
    maxY: centerY + height / 2,
    width,
    height,
  };
}

function fitBoundsToViewport(bounds: PlanBounds, aspectRatio: number): PlanBounds {
  const safeAspect = Number.isFinite(aspectRatio) && aspectRatio > 0 ? aspectRatio : 1;
  const boundsAspect = bounds.width / bounds.height;
  if (Math.abs(boundsAspect - safeAspect) < 0.01) {
    return bounds;
  }
  const centerX = bounds.minX + bounds.width / 2;
  const centerY = bounds.minY + bounds.height / 2;
  if (boundsAspect > safeAspect) {
    const height = bounds.width / safeAspect;
    return {
      minX: bounds.minX,
      maxX: bounds.maxX,
      minY: centerY - height / 2,
      maxY: centerY + height / 2,
      width: bounds.width,
      height,
    };
  }
  const width = bounds.height * safeAspect;
  return {
    minX: centerX - width / 2,
    maxX: centerX + width / 2,
    minY: bounds.minY,
    maxY: bounds.maxY,
    width,
    height: bounds.height,
  };
}

function boundsForPoints(points: [number, number][]): PlanBounds | null {
  if (!points.length) return null;
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const [x, y] of points) {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  return {
    minX,
    minY,
    maxX,
    maxY,
    width: Math.max(maxX - minX, 1),
    height: Math.max(maxY - minY, 1),
  };
}

function densestClusterBounds(points: [number, number][], bounds: PlanBounds): PlanBounds | null {
  if (points.length < 8) return null;
  const cols = 4;
  const rows = 3;
  const cells = new Map<string, [number, number][]>();
  for (const point of points) {
    const col = Math.max(0, Math.min(cols - 1, Math.floor(((point[0] - bounds.minX) / bounds.width) * cols)));
    const row = Math.max(0, Math.min(rows - 1, Math.floor(((point[1] - bounds.minY) / bounds.height) * rows)));
    const key = `${col}:${row}`;
    const bucket = cells.get(key);
    if (bucket) bucket.push(point);
    else cells.set(key, [point]);
  }
  let best: [number, number][] | null = null;
  for (const bucket of cells.values()) {
    if (!best || bucket.length > best.length) best = bucket;
  }
  return best ? boundsForPoints(best) : null;
}

function labelFontSize(maxDimension: number): string {
  if (maxDimension > 40000) return "10px";
  if (maxDimension > 12000) return "11px";
  if (maxDimension > 4000) return "12px";
  return "13px";
}

function layerStyle(layer: string, hasLabel = false) {
  switch (layer) {
    case "parcel-fill":
      return {
        stroke: "none",
        strokeOpacity: 0,
        strokeWidth: 0,
        fill: "#f8fafc",
        fillOpacity: 0.95,
      };
    case "parcel-outline":
      return {
        stroke: hasLabel ? "#475569" : "#334155",
        strokeOpacity: 0.92,
        strokeWidth: 2.4,
        fill: "none",
        fillOpacity: 0,
      };
    case "road":
      return {
        stroke: "#0f172a",
        strokeOpacity: 1,
        strokeWidth: 1.8,
        fill: "#111827",
        fillOpacity: 0.96,
      };
    case "easements":
      return {
        stroke: "#dc2626",
        strokeOpacity: 0.9,
        strokeWidth: 1.4,
        fill: "#fecaca",
        fillOpacity: 0.35,
      };
    case "lots":
      return {
        stroke: "#1d4ed8",
        strokeOpacity: 0.98,
        strokeWidth: 1.2,
        fill: "#bfdbfe",
        fillOpacity: 0.78,
      };
    default:
      return {
        stroke: "#64748b",
        strokeOpacity: 1,
        strokeWidth: 1,
        fill: "#f8fafc",
        fillOpacity: 0.25,
      };
  }
}
