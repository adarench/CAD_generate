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
  const areaSqft = source.areaSqft ?? estimateAreaSqft(source.geometry);
  const areaAcres = source.areaAcres ?? (areaSqft ? areaSqft / 43560 : null);

  return {
    id: source.id ?? `${slug(source.county ?? "utah")}-${source.apn ?? "unknown"}`,
    state: "UT",
    county: source.county ?? "Unknown",
    apn: source.apn ?? null,
    sourceProvider: source.sourceProvider ?? "Unknown",
    sourceDataset: source.sourceDataset ?? "parcel-source",
    sourceObjectId: source.sourceObjectId ?? null,
    geometryGeoJSON: source.geometry,
    centroid,
    areaSqft,
    areaAcres,
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

function estimateAreaSqft(geometry: Polygon | MultiPolygon) {
  const rings = geometry.type === "Polygon" ? geometry.coordinates : geometry.coordinates.flat();
  const squareDegrees = rings.reduce((sum, ring) => sum + Math.abs(ringArea(ring)), 0);
  if (squareDegrees <= 0) return null;

  const centroid = estimateCentroid(geometry);
  const feetPerDegreeLat = 364000;
  const feetPerDegreeLng = feetPerDegreeLat * Math.cos((centroid.lat * Math.PI) / 180);
  return Math.round(squareDegrees * feetPerDegreeLat * Math.max(feetPerDegreeLng, 1));
}

function ringArea(ring: number[][]) {
  if (ring.length < 3) return 0;
  let area = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    const [x1, y1] = ring[index];
    const [x2, y2] = ring[index + 1];
    area += x1 * y2 - x2 * y1;
  }
  return area / 2;
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
