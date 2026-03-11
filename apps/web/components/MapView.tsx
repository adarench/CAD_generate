"use client";

import L, { type LeafletMouseEvent, type PathOptions } from "leaflet";
import { useEffect, useMemo } from "react";
import { GeoJSON, MapContainer, Pane, TileLayer, ZoomControl, useMap, useMapEvents } from "react-leaflet";

import type { BasemapMode, MapViewState } from "@/lib/mapConfig";
import {
  AERIAL_BASEMAP_ATTRIBUTION,
  AERIAL_BASEMAP_TILE_URL,
  DEFAULT_MAP_VIEW,
  GIS_BASEMAP_ATTRIBUTION,
  GIS_BASEMAP_SUBDOMAINS,
  GIS_REFERENCE_TILE_URL,
  GIS_BASEMAP_TILE_URL,
} from "@/lib/mapConfig";
import { PARCEL_DEBUG_ENABLED } from "@/lib/parcelDebug";

type FeatureCollection = GeoJSON.FeatureCollection;
type MapVisualMode = "discovery" | "studio";

interface MapViewProps {
  onParcelClick?: (lat: number, lng: number) => void;
  onVisibleParcelClick?: (parcelId: string) => void;
  onParcelHover?: (parcelId: string | null) => void;
  onViewportIdle?: (viewport: {
    minLng: number;
    minLat: number;
    maxLng: number;
    maxLat: number;
    zoom: number;
  }) => void;
  parcelGeometry?: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
  contextGeoJSON?: FeatureCollection | null;
  resultGeoJSON?: FeatureCollection | null;
  center?: { lng: number; lat: number } | null;
  viewState?: MapViewState | null;
  hoveredParcelId?: string | null;
  selectedParcelId?: string | null;
  selectedParcelApn?: string | null;
  basemapMode?: BasemapMode;
  visualMode?: MapVisualMode;
  onMapStatusChange?: (status: { state: "booting" | "ready" | "error"; message?: string }) => void;
}

const EMPTY_COLLECTION: FeatureCollection = { type: "FeatureCollection", features: [] };

const CONTEXT_STYLE: PathOptions = {
  color: "#0f172a",
  weight: 1.9,
  opacity: 0.9,
  fillColor: "#94a3b8",
  fillOpacity: 0,
};

const HOVER_STYLE: PathOptions = {
  color: "#0ea5e9",
  weight: 3.4,
  opacity: 1,
  fillColor: "#38bdf8",
  fillOpacity: 0.14,
};

const SELECTED_STYLE: PathOptions = {
  color: "#f97316",
  weight: 4.1,
  opacity: 1,
  fillColor: "#fb923c",
  fillOpacity: 0.18,
};

const PARCEL_STYLE: PathOptions = {
  color: "#f97316",
  weight: 4.4,
  opacity: 1,
  fillColor: "#fb923c",
  fillOpacity: 0.22,
};

export function MapView({
  onParcelClick,
  onVisibleParcelClick,
  onParcelHover,
  onViewportIdle,
  parcelGeometry,
  contextGeoJSON,
  resultGeoJSON,
  center,
  viewState,
  hoveredParcelId,
  selectedParcelId,
  selectedParcelApn,
  basemapMode = "gis",
  visualMode = "discovery",
  onMapStatusChange,
}: MapViewProps) {
  const parcelCollection = useMemo<FeatureCollection>(() => {
    if (!parcelGeometry) {
      return EMPTY_COLLECTION;
    }
    return {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {
            apn: selectedParcelApn ?? null,
          },
          geometry: parcelGeometry,
        },
      ],
    };
  }, [parcelGeometry, selectedParcelApn]);

  const hoveredCollection = useMemo(
    () => filterByParcelId(contextGeoJSON, hoveredParcelId),
    [contextGeoJSON, hoveredParcelId]
  );
  const selectedCollection = useMemo(
    () => filterByParcelId(contextGeoJSON, selectedParcelId),
    [contextGeoJSON, selectedParcelId]
  );

  useEffect(() => {
    if (PARCEL_DEBUG_ENABLED) {
      console.log("[parcel-map] feature collections", {
        contextCount: contextGeoJSON?.features.length ?? 0,
        selectedCount: parcelCollection.features.length,
        resultCount: resultGeoJSON?.features.length ?? 0,
      });
    }
  }, [contextGeoJSON, parcelCollection.features.length, resultGeoJSON]);

  const basemapConfig = tileConfigForMode(basemapMode);

  const initialCenter: [number, number] = center
    ? [center.lat, center.lng]
    : viewState
      ? [viewState.lat, viewState.lng]
      : [DEFAULT_MAP_VIEW.lat, DEFAULT_MAP_VIEW.lng];

  return (
    <div className="absolute inset-0">
      <MapContainer
        center={initialCenter}
        zoom={center ? 14 : viewState?.zoom ?? DEFAULT_MAP_VIEW.zoom}
        zoomControl={false}
        className={`h-full w-full ${visualMode === "studio" ? "studio-map" : "discovery-map"}`}
        whenReady={() => onMapStatusChange?.({ state: "ready" })}
      >
        {basemapConfig ? (
          <TileLayer
            attribution={basemapConfig.attribution}
            opacity={basemapConfig.opacity ?? 1}
            subdomains={basemapConfig.subdomains}
            url={basemapConfig.url}
          />
        ) : null}
        {basemapConfig?.referenceUrl ? (
          <TileLayer
            attribution={basemapConfig.referenceAttribution ?? basemapConfig.attribution}
            opacity={basemapConfig.referenceOpacity ?? 1}
            url={basemapConfig.referenceUrl}
          />
        ) : null}
        <ZoomControl position="topright" />
        <MapRuntimeBridge
          center={center}
          viewState={viewState}
          parcelCollection={parcelCollection}
          resultGeoJSON={resultGeoJSON}
          onMapStatusChange={onMapStatusChange}
          onViewportIdle={onViewportIdle}
          onParcelClick={onParcelClick}
        />

        <Pane name="context-fill" style={{ zIndex: 350 }}>
          {contextGeoJSON?.features.length ? (
            <GeoJSON
              data={contextGeoJSON as any}
              style={() => contextStyle(visualMode)}
              onEachFeature={(feature, layer) => {
                layer.on({
                  mouseover: () => onParcelHover?.(String(feature.properties?.id ?? null)),
                  mouseout: () => onParcelHover?.(null),
                  click: (event: LeafletMouseEvent) => {
                    L.DomEvent.stop(event.originalEvent);
                    const parcelId = feature.properties?.id;
                    if (parcelId) {
                      onVisibleParcelClick?.(String(parcelId));
                    }
                  },
                });
                const apn = feature.properties?.apn;
                if (apn) {
                  layer.bindTooltip(String(apn), {
                    sticky: true,
                    direction: "top",
                    offset: L.point(0, -8),
                    className: "parcel-apn-tooltip",
                  });
                }
              }}
            />
          ) : null}
        </Pane>

        <Pane name="context-hover" style={{ zIndex: 360 }}>
          {hoveredCollection?.features.length ? (
            <GeoJSON data={hoveredCollection as any} style={() => hoverStyle(visualMode)} />
          ) : null}
        </Pane>

        <Pane name="context-selected" style={{ zIndex: 370 }}>
          {selectedCollection?.features.length ? (
            <GeoJSON
              data={selectedCollection as any}
              style={() => selectedStyle(visualMode)}
              onEachFeature={(feature, layer) => bindSelectedParcelLabel(feature, layer)}
            />
          ) : null}
        </Pane>

        <Pane name="selected-parcel" style={{ zIndex: 380 }}>
          {parcelCollection.features.length ? (
            <GeoJSON
              data={parcelCollection as any}
              style={() => parcelStyle(visualMode)}
              onEachFeature={(feature, layer) => bindSelectedParcelLabel(feature, layer)}
            />
          ) : null}
        </Pane>

        <Pane name="results" style={{ zIndex: 390 }}>
          {resultGeoJSON?.features.length ? (
            <GeoJSON
              data={resultGeoJSON as any}
              style={(feature) => resultStyle(feature, visualMode)}
              pointToLayer={(feature, latlng) => {
                const layerName = String(feature.properties?.layer ?? "");
                if (layerName === "lot_labels") {
                  const marker = L.circleMarker(latlng, {
                    radius: 1,
                    opacity: 0,
                    fillOpacity: 0,
                  });
                  const text = String(feature.properties?.text ?? "");
                  if (text) {
                    marker.bindTooltip(text, {
                      permanent: true,
                      direction: "center",
                      className: "lot-label",
                    });
                  }
                  return marker;
                }
                return L.circleMarker(latlng, {
                  radius: 3,
                  color: "#e2e8f0",
                  weight: 1,
                  fillColor: "#1e293b",
                  fillOpacity: 0.75,
                });
              }}
            />
          ) : null}
        </Pane>
      </MapContainer>
    </div>
  );
}

function tileConfigForMode(mode: BasemapMode) {
  switch (mode) {
    case "gis":
      return {
        url: GIS_BASEMAP_TILE_URL,
        attribution: GIS_BASEMAP_ATTRIBUTION,
        subdomains: GIS_BASEMAP_SUBDOMAINS,
        referenceUrl: GIS_REFERENCE_TILE_URL || undefined,
        referenceAttribution: GIS_BASEMAP_ATTRIBUTION,
        opacity: 0.78,
        referenceOpacity: 0.72,
      };
    case "aerial":
      return {
        url: AERIAL_BASEMAP_TILE_URL,
        attribution: AERIAL_BASEMAP_ATTRIBUTION,
      };
    default:
      return null;
  }
}

function MapRuntimeBridge({
  center,
  viewState,
  parcelCollection,
  resultGeoJSON,
  onMapStatusChange,
  onViewportIdle,
  onParcelClick,
}: {
  center?: { lng: number; lat: number } | null;
  viewState?: MapViewState | null;
  parcelCollection: FeatureCollection;
  resultGeoJSON?: FeatureCollection | null;
  onMapStatusChange?: (status: { state: "booting" | "ready" | "error"; message?: string }) => void;
  onViewportIdle?: (viewport: {
    minLng: number;
    minLat: number;
    maxLng: number;
    maxLat: number;
    zoom: number;
  }) => void;
  onParcelClick?: (lat: number, lng: number) => void;
}) {
  const map = useMapEvents({
    click(event) {
      onParcelClick?.(event.latlng.lat, event.latlng.lng);
    },
    moveend() {
      reportViewport(map, onViewportIdle);
    },
    zoomend() {
      reportViewport(map, onViewportIdle);
    },
  });

  useEffect(() => {
    map.invalidateSize();
    reportViewport(map, onViewportIdle);
  }, [map, onMapStatusChange, onViewportIdle]);

  useEffect(() => {
    if (!center) return;
    map.flyTo([center.lat, center.lng], 16, { duration: 0.65 });
  }, [center, map]);

  useEffect(() => {
    if (center || !viewState) return;
    map.flyTo([viewState.lat, viewState.lng], viewState.zoom, { duration: 0.65 });
  }, [center, map, viewState]);

  useEffect(() => {
    if (!parcelCollection.features.length) return;
    const bounds = collectionBounds(parcelCollection);
    if (bounds) {
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 17 });
    }
  }, [map, parcelCollection]);

  useEffect(() => {
    if (parcelCollection.features.length || !resultGeoJSON?.features.length) return;
    const bounds = collectionBounds(resultGeoJSON);
    if (bounds) {
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 16 });
    }
  }, [map, parcelCollection.features.length, resultGeoJSON]);

  return null;
}

function reportViewport(
  map: L.Map,
  callback:
    | ((
        viewport: {
          minLng: number;
          minLat: number;
          maxLng: number;
          maxLat: number;
          zoom: number;
        }
      ) => void)
    | undefined
) {
  if (!callback) return;
  const bounds = map.getBounds();
  callback({
    minLng: bounds.getWest(),
    minLat: bounds.getSouth(),
    maxLng: bounds.getEast(),
    maxLat: bounds.getNorth(),
    zoom: map.getZoom(),
  });
}

function filterByParcelId(collection: FeatureCollection | null | undefined, parcelId: string | null | undefined) {
  if (!collection?.features.length || !parcelId) {
    return null;
  }
  const features = collection.features.filter((feature) => feature.properties?.id === parcelId);
  return features.length ? ({ type: "FeatureCollection", features } as FeatureCollection) : null;
}

function bindSelectedParcelLabel(feature: GeoJSON.Feature, layer: L.Layer) {
  const apn = feature.properties?.apn;
  if (!apn || !("bindTooltip" in layer)) {
    return;
  }
  layer.bindTooltip(String(apn), {
    permanent: true,
    direction: "center",
    className: "parcel-apn-label",
  });
}

function contextStyle(visualMode: MapVisualMode): PathOptions {
  if (visualMode === "studio") {
    return {
      color: "#94a3b8",
      weight: 1,
      opacity: 0.55,
      fillColor: "#cbd5e1",
      fillOpacity: 0.03,
    };
  }
  return CONTEXT_STYLE;
}

function hoverStyle(visualMode: MapVisualMode): PathOptions {
  if (visualMode === "studio") {
    return {
      color: "#0f172a",
      weight: 3.4,
      opacity: 1,
      fillColor: "#38bdf8",
      fillOpacity: 0.14,
    };
  }
  return HOVER_STYLE;
}

function selectedStyle(visualMode: MapVisualMode): PathOptions {
  if (visualMode === "studio") {
    return {
      color: "#020617",
      weight: 3.8,
      opacity: 1,
      fillColor: "#94a3b8",
      fillOpacity: 0.1,
    };
  }
  return SELECTED_STYLE;
}

function parcelStyle(visualMode: MapVisualMode): PathOptions {
  if (visualMode === "studio") {
    return {
      color: "#0f172a",
      weight: 3.2,
      opacity: 1,
      fillColor: "#e2e8f0",
      fillOpacity: 0.08,
    };
  }
  return PARCEL_STYLE;
}

function resultStyle(feature: GeoJSON.Feature | undefined, visualMode: MapVisualMode): PathOptions {
  const layer = String(feature?.properties?.layer ?? "");
  if (visualMode === "studio") {
    switch (layer) {
      case "road":
        return {
          color: "#0f172a",
          weight: 2.4,
          opacity: 1,
          fillColor: "#1e293b",
          fillOpacity: 0.84,
        };
      case "easements":
        return {
          color: "#b45309",
          weight: 1.8,
          opacity: 0.9,
          fillColor: "#f59e0b",
          fillOpacity: 0.08,
          dashArray: "6 4",
        };
      case "lots":
        return {
          color: "#0f172a",
          weight: 1.35,
          opacity: 0.9,
          fillColor: "#67e8f9",
          fillOpacity: 0.18,
        };
      case "parcel":
        return {
          color: "#334155",
          weight: 1.8,
          opacity: 0.9,
          fillColor: "#cbd5e1",
          fillOpacity: 0.05,
        };
      default:
        return {
          color: "#334155",
          weight: 1.2,
          opacity: 0.8,
          fillOpacity: 0.04,
        };
    }
  }
  switch (layer) {
    case "road":
      return {
        color: "#111827",
        weight: 2.5,
        opacity: 1,
        fillColor: "#0f172a",
        fillOpacity: 0.65,
      };
    case "easements":
      return {
        color: "#dc2626",
        weight: 2,
        opacity: 0.9,
        fillColor: "#ef4444",
        fillOpacity: 0.16,
      };
    case "lots":
      return {
        color: "#60a5fa",
        weight: 1.6,
        opacity: 0.95,
        fillColor: "#3b82f6",
        fillOpacity: 0.14,
      };
    case "parcel":
      return {
        color: "#94a3b8",
        weight: 2,
        opacity: 1,
        fillColor: "#64748b",
        fillOpacity: 0.12,
      };
    default:
      return {
        color: "#cbd5e1",
        weight: 1.6,
        opacity: 0.9,
        fillOpacity: 0.08,
      };
  }
}

function collectionBounds(collection: FeatureCollection): L.LatLngBoundsExpression | null {
  const coords: number[][] = [];
  for (const feature of collection.features) {
    const geometry = feature.geometry;
    if (!geometry) continue;
    if (geometry.type === "Polygon") {
      geometry.coordinates.forEach((ring) => ring.forEach((point) => coords.push(point)));
    }
    if (geometry.type === "MultiPolygon") {
      geometry.coordinates.forEach((polygon) =>
        polygon.forEach((ring) => ring.forEach((point) => coords.push(point)))
      );
    }
    if (geometry.type === "Point") {
      coords.push(geometry.coordinates as number[]);
    }
  }
  if (!coords.length) return null;
  const lngs = coords.map((point) => point[0]);
  const lats = coords.map((point) => point[1]);
  return [
    [Math.min(...lats), Math.min(...lngs)],
    [Math.max(...lats), Math.max(...lngs)],
  ];
}
