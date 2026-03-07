"use client";

import { useEffect, useMemo, useRef } from "react";
import maplibregl, { LngLatBoundsLike } from "maplibre-gl";

type FeatureCollection = GeoJSON.FeatureCollection;

interface MapViewProps {
  onParcelClick?: (lat: number, lng: number) => void;
  parcelGeometry?: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
  resultGeoJSON?: FeatureCollection | null;
  center?: { lng: number; lat: number } | null;
}

const EMPTY_COLLECTION: FeatureCollection = { type: "FeatureCollection", features: [] };

export function MapView({ onParcelClick, parcelGeometry, resultGeoJSON, center }: MapViewProps) {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const clickRef = useRef(onParcelClick);

  clickRef.current = onParcelClick;

  const parcelCollection = useMemo<FeatureCollection>(() => {
    if (!parcelGeometry) {
      return EMPTY_COLLECTION;
    }
    return {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {},
          geometry: parcelGeometry,
        },
      ],
    };
  }, [parcelGeometry]);

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://demotiles.maplibre.org/style.json",
      center: center ? [center.lng, center.lat] : [-111.8, 40.3],
      zoom: center ? 14 : 7,
    });

    map.on("load", () => {
      map.addSource("parcel", {
        type: "geojson",
        data: EMPTY_COLLECTION,
      });
      map.addSource("result", {
        type: "geojson",
        data: EMPTY_COLLECTION,
      });

      map.addLayer({
        id: "parcel-fill",
        type: "fill",
        source: "parcel",
        paint: {
          "fill-color": "#94a3b8",
          "fill-opacity": 0.18,
        },
      });
      map.addLayer({
        id: "parcel-outline",
        type: "line",
        source: "parcel",
        paint: {
          "line-color": "#e2e8f0",
          "line-width": 3,
        },
      });
      map.addLayer({
        id: "result-fill",
        type: "fill",
        source: "result",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "fill-color": [
            "match",
            ["get", "layer"],
            "road",
            "#0f172a",
            "easements",
            "#ef4444",
            "lots",
            "#3b82f6",
            "parcel",
            "#64748b",
            "#334155",
          ],
          "fill-opacity": [
            "match",
            ["get", "layer"],
            "road",
            0.65,
            "easements",
            0.18,
            "lots",
            0.16,
            0.12,
          ],
        },
      });
      map.addLayer({
        id: "result-outline",
        type: "line",
        source: "result",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "line-color": [
            "match",
            ["get", "layer"],
            "road",
            "#111827",
            "easements",
            "#dc2626",
            "lots",
            "#60a5fa",
            "#94a3b8",
          ],
          "line-width": 2,
        },
      });
      map.addLayer({
        id: "result-labels",
        type: "symbol",
        source: "result",
        filter: ["==", ["get", "layer"], "lot_labels"],
        layout: {
          "text-field": ["get", "text"],
          "text-size": 11,
        },
        paint: {
          "text-color": "#e2e8f0",
          "text-halo-color": "#0f172a",
          "text-halo-width": 1.2,
        },
      });
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("click", (event) => {
      clickRef.current?.(event.lngLat.lat, event.lngLat.lng);
    });

    mapRef.current = map;
    return () => map.remove();
  }, [center]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    const source = map.getSource("parcel") as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(parcelCollection);
      fitToFeatures(map, parcelCollection);
    }
  }, [parcelCollection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    const source = map.getSource("result") as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(resultGeoJSON ?? EMPTY_COLLECTION);
      if (resultGeoJSON?.features?.length) {
        fitToFeatures(map, resultGeoJSON);
      }
    }
  }, [resultGeoJSON]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !center) return;
    map.easeTo({ center: [center.lng, center.lat], zoom: 14, duration: 600 });
  }, [center]);

  return <div ref={mapContainer} className="h-full w-full" />;
}

function fitToFeatures(map: maplibregl.Map, collection: FeatureCollection) {
  const bounds = geojsonBounds(collection);
  if (!bounds) return;
  map.fitBounds(bounds, { padding: 48, duration: 500, maxZoom: 16 });
}

function geojsonBounds(collection: FeatureCollection): LngLatBoundsLike | null {
  const coords: number[][] = [];
  for (const feature of collection.features) {
    const geometry = feature.geometry;
    if (!geometry) continue;
    if (geometry.type === "Polygon") {
      geometry.coordinates[0]?.forEach((point) => coords.push(point));
    }
    if (geometry.type === "MultiPolygon") {
      geometry.coordinates.forEach((polygon) =>
        polygon[0]?.forEach((point) => coords.push(point))
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
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)],
  ];
}
