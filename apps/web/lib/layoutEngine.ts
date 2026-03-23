import type { ParcelRecord } from "@/lib/parcels";

export interface LayoutResultSummary {
  rank: number;
  generatorType: string;
  score: number;
  lotCount: number;
  totalRoadFt: number;
  totalLotAreaSqft: number;
  avgLotAreaSqft: number;
  devAreaRatio: number;
}

export interface LayoutGenerateResponse {
  parcelId: string;
  areaAcres: number;
  results: LayoutResultSummary[];
  topResultGeoJSON: GeoJSON.FeatureCollection;
  priorUsed: boolean;
}

export interface LayoutGenerateRequest {
  parcel: {
    id: string;
    state: "UT";
    county: string;
    apn?: string | null;
    geometry: { type: string; coordinates: unknown };
    centroid: { lng: number; lat: number };
    areaSqft?: number | null;
    areaAcres?: number | null;
    address?: string | null;
    ownerName?: string | null;
    sourceProvider: string;
    sourceDataset: string;
    sourceObjectId?: string | null;
    rawAttributes: Record<string, unknown>;
    fetchedAt: string;
  };
  nCandidates?: number;
  nTop?: number;
  seed?: number;
  roadWidthFt?: number;
  lotDepthFt?: number;
  minFrontageFt?: number;
  usePrior?: boolean;
}

export function parcelToLayoutRequest(parcel: ParcelRecord): LayoutGenerateRequest {
  return {
    parcel: {
      id: parcel.id,
      state: parcel.state,
      county: parcel.county,
      apn: parcel.apn,
      geometry: parcel.geometryGeoJSON,
      centroid: parcel.centroid,
      areaSqft: parcel.areaSqft,
      areaAcres: parcel.areaAcres,
      address: parcel.address,
      ownerName: parcel.ownerName,
      sourceProvider: parcel.sourceProvider,
      sourceDataset: parcel.sourceDataset,
      sourceObjectId: parcel.sourceObjectId,
      rawAttributes: parcel.rawAttributes ?? {},
      fetchedAt: parcel.fetchedAt,
    },
  };
}

export async function generateLayout(
  parcel: ParcelRecord,
  opts?: Partial<Omit<LayoutGenerateRequest, "parcel">>
): Promise<LayoutGenerateResponse> {
  const payload: LayoutGenerateRequest = {
    ...parcelToLayoutRequest(parcel),
    ...opts,
  };

  const response = await fetch("/api/layout/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let detail = "Layout generation failed.";
    try {
      const body = await response.json();
      detail = body.detail ?? body.error ?? detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }

  return response.json() as Promise<LayoutGenerateResponse>;
}
