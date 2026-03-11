import type { OptimizationResponse, ParcelRecord } from "@/lib/parcels";

const FEET_PER_DEGREE_LAT = 364000;

export type PlanPoint = [number, number];

export type PlanPolygon = {
  type: "Polygon";
  rings: PlanPoint[][];
};

export type PlanMultiPolygon = {
  type: "MultiPolygon";
  polygons: PlanPoint[][][];
};

export type PlanPointGeometry = {
  type: "Point";
  coordinates: PlanPoint;
};

export type PlanGeometry = PlanPolygon | PlanMultiPolygon | PlanPointGeometry;

export type PlanFeature = {
  id: string;
  layer: string;
  geometry: PlanGeometry;
  text?: string | null;
};

export type PlanBounds = {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  width: number;
  height: number;
};

type PlanProjection = {
  originLng: number;
  originLat: number;
  feetPerDegreeLng: number;
  feetPerDegreeLat: number;
};

export function projectParcelGeometry(parcel: ParcelRecord | null | undefined): PlanFeature[] {
  if (!parcel) return [];
  const projection = projectionFromParcel(parcel);
  const geometry = projectGeometry(parcel.geometryGeoJSON, projection);
  return [
    {
      id: `${parcel.id}-parcel`,
      layer: "parcel",
      geometry,
      text: parcel.apn,
    },
  ];
}

export function projectResultGeometry(
  parcel: ParcelRecord | null | undefined,
  result: OptimizationResponse | null | undefined,
  visibleLayers: string[]
): PlanFeature[] {
  if (!parcel || !result?.resultGeoJSON) return [];
  const projection = projectionFromParcel(parcel);
  return result.resultGeoJSON.features
    .filter((feature) => visibleLayers.includes(String(feature.properties?.layer ?? "")))
    .map((feature, index) => ({
      id: String(feature.properties?.id ?? `${feature.properties?.layer ?? "feature"}-${index}`),
      layer: String(feature.properties?.layer ?? "unknown"),
      text: feature.properties?.text ? String(feature.properties.text) : null,
      geometry: projectGeometry(feature.geometry, projection),
    }));
}

export function boundsForPlanFeatures(features: PlanFeature[]): PlanBounds | null {
  if (!features.length) return null;
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const feature of features) {
    for (const point of iterateGeometryPoints(feature.geometry)) {
      minX = Math.min(minX, point[0]);
      minY = Math.min(minY, point[1]);
      maxX = Math.max(maxX, point[0]);
      maxY = Math.max(maxY, point[1]);
    }
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
    return null;
  }

  return normalizeBounds({ minX, minY, maxX, maxY });
}

export function padBounds(bounds: PlanBounds, ratio = 0.08): PlanBounds {
  const dx = Math.max(bounds.width * ratio, 18);
  const dy = Math.max(bounds.height * ratio, 18);
  return normalizeBounds({
    minX: bounds.minX - dx,
    minY: bounds.minY - dy,
    maxX: bounds.maxX + dx,
    maxY: bounds.maxY + dy,
  });
}

export function flipY(y: number, bounds: PlanBounds): number {
  return bounds.minY + bounds.maxY - y;
}

export function featurePathData(feature: PlanFeature): string | null {
  if (feature.geometry.type === "Point") return null;
  if (feature.geometry.type === "Polygon") {
    return polygonPath(feature.geometry.rings);
  }
  return feature.geometry.polygons.map((polygon) => polygonPath(polygon)).join(" ");
}

function polygonPath(rings: PlanPoint[][]): string {
  return rings
    .map((ring) =>
      ring
        .map((point, index) => `${index === 0 ? "M" : "L"} ${point[0]} ${point[1]}`)
        .join(" ")
        .concat(" Z")
    )
    .join(" ");
}

function projectionFromParcel(parcel: ParcelRecord): PlanProjection {
  const feetPerDegreeLng = FEET_PER_DEGREE_LAT * Math.cos((parcel.centroid.lat * Math.PI) / 180);
  return {
    originLng: parcel.centroid.lng,
    originLat: parcel.centroid.lat,
    feetPerDegreeLng: Math.max(feetPerDegreeLng, 1),
    feetPerDegreeLat: FEET_PER_DEGREE_LAT,
  };
}

function projectGeometry(
  geometry: GeoJSON.Geometry | GeoJSON.Polygon | GeoJSON.MultiPolygon,
  projection: PlanProjection
): PlanGeometry {
  if (geometry.type === "Polygon") {
    return {
      type: "Polygon",
      rings: geometry.coordinates.map((ring) => ring.map((point) => toPlanPoint(point, projection))),
    };
  }
  if (geometry.type === "MultiPolygon") {
    return {
      type: "MultiPolygon",
      polygons: geometry.coordinates.map((polygon) =>
        polygon.map((ring) => ring.map((point) => toPlanPoint(point, projection)))
      ),
    };
  }
  if (geometry.type === "Point") {
    return {
      type: "Point",
      coordinates: toPlanPoint(geometry.coordinates, projection),
    };
  }
  throw new Error(`Unsupported Studio plan geometry type: ${geometry.type}`);
}

function toPlanPoint(point: number[], projection: PlanProjection): PlanPoint {
  const [lng, lat] = point;
  return [
    (lng - projection.originLng) * projection.feetPerDegreeLng,
    (lat - projection.originLat) * projection.feetPerDegreeLat,
  ];
}

function* iterateGeometryPoints(geometry: PlanGeometry): Generator<PlanPoint> {
  if (geometry.type === "Point") {
    yield geometry.coordinates;
    return;
  }
  if (geometry.type === "Polygon") {
    for (const ring of geometry.rings) {
      yield* ring;
    }
    return;
  }
  for (const polygon of geometry.polygons) {
    for (const ring of polygon) {
      yield* ring;
    }
  }
}

function normalizeBounds(input: {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}): PlanBounds {
  const width = Math.max(input.maxX - input.minX, 1);
  const height = Math.max(input.maxY - input.minY, 1);
  return {
    minX: input.minX,
    minY: input.minY,
    maxX: input.maxX,
    maxY: input.maxY,
    width,
    height,
  };
}
