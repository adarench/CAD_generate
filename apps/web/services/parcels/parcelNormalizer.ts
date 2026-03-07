import type { Feature, MultiPolygon, Polygon } from "geojson";

export type ParcelRecord = {
  id: string;
  state: "UT";
  county: string;
  apn: string | null;
  sourceProvider: string;
  sourceDataset: string;
  sourceObjectId: string | null;
  geometryGeoJSON: Polygon | MultiPolygon;
  centroid: { lng: number; lat: number };
  areaSqft: number | null;
  areaAcres: number | null;
  address: string | null;
  ownerName: string | null;
  zoningCode: string | null;
  landUse: string | null;
  rawAttributes: Record<string, unknown>;
  fetchedAt: string;
};

export type ParcelSourcePayload = {
  id?: string;
  county?: string;
  apn?: string | null;
  geometry?: Polygon | MultiPolygon;
  sourceProvider?: string;
  sourceDataset?: string;
  sourceObjectId?: string | null;
  areaSqft?: number | null;
  areaAcres?: number | null;
  address?: string | null;
  ownerName?: string | null;
  zoningCode?: string | null;
  landUse?: string | null;
  rawAttributes?: Record<string, unknown>;
  fetchedAt?: string;
};

export function normalizeParcel(source: ParcelSourcePayload): ParcelRecord {
  if (!source.geometry) {
    throw new Error("Parcel geometry is required for normalization.");
  }

  const centroid = estimateCentroid(source.geometry);

  return {
    id: source.id ?? `${slug(source.county ?? "utah")}-${source.apn ?? "unknown"}`,
    state: "UT",
    county: source.county ?? "Unknown",
    apn: source.apn ?? null,
    sourceProvider: source.sourceProvider ?? "Local Demo",
    sourceDataset: source.sourceDataset ?? "demo-parcels",
    sourceObjectId: source.sourceObjectId ?? null,
    geometryGeoJSON: source.geometry,
    centroid,
    areaSqft: source.areaSqft ?? null,
    areaAcres: source.areaAcres ?? null,
    address: source.address ?? null,
    ownerName: source.ownerName ?? null,
    zoningCode: source.zoningCode ?? null,
    landUse: source.landUse ?? null,
    rawAttributes: source.rawAttributes ?? {},
    fetchedAt: source.fetchedAt ?? new Date().toISOString(),
  };
}

export function featureToNormalizedParcel(
  feature: Feature<Polygon | MultiPolygon>,
  attrs: Record<string, unknown>
): ParcelRecord {
  return normalizeParcel({
    id: String(attrs.id ?? feature.id ?? `${attrs.county ?? "utah"}-${attrs.apn ?? "parcel"}`),
    county: asString(attrs.county),
    apn: asNullableString(attrs.apn),
    geometry: feature.geometry,
    sourceProvider: asString(attrs.sourceProvider) ?? "UGRC",
    sourceDataset: asString(attrs.sourceDataset) ?? "utah-parcels",
    sourceObjectId: asNullableString(attrs.sourceObjectId),
    areaSqft: asNullableNumber(attrs.areaSqft),
    areaAcres: asNullableNumber(attrs.areaAcres),
    address: asNullableString(attrs.address),
    ownerName: asNullableString(attrs.ownerName),
    zoningCode: asNullableString(attrs.zoningCode),
    landUse: asNullableString(attrs.landUse),
    rawAttributes: attrs,
  });
}

function estimateCentroid(geometry: Polygon | MultiPolygon) {
  const rings = geometry.type === "Polygon" ? geometry.coordinates : geometry.coordinates[0];
  const points = rings[0] ?? [];
  const totals = points.reduce(
    (acc, point) => {
      acc.lng += point[0];
      acc.lat += point[1];
      return acc;
    },
    { lng: 0, lat: 0 }
  );
  const count = Math.max(points.length, 1);
  return {
    lng: totals.lng / count,
    lat: totals.lat / count,
  };
}

function slug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function asString(value: unknown) {
  return typeof value === "string" ? value : undefined;
}

function asNullableString(value: unknown) {
  return typeof value === "string" ? value : null;
}

function asNullableNumber(value: unknown) {
  return typeof value === "number" ? value : null;
}
