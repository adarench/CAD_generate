import type {
  BedrockParcel,
  DiscoveryParcelRecord,
  ParcelLookupResponse,
  PipelineRun,
  PipelineRunSummary,
} from "@/lib/parcels";
import { parcelLoadRequestFromDiscovery } from "@/lib/parcels";
import { PARCEL_DEBUG_ENABLED } from "@/lib/parcelDebug";

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let payload: unknown = null;
    let detail = "Request failed.";
    try {
      payload = await response.json();
      detail = extractErrorMessage(payload) ?? detail;
    } catch {
      try {
        detail = await response.text();
      } catch {
        detail = "Request failed.";
      }
    }
    throw new ApiError(detail, response.status, payload);
  }
  return response.json() as Promise<T>;
}

function extractErrorMessage(payload: unknown): string | null {
  if (typeof payload === "string") return payload;
  if (!payload || typeof payload !== "object") return null;
  const record = payload as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  if (record.detail && typeof record.detail === "object") {
    const detail = record.detail as Record<string, unknown>;
    if (typeof detail.message === "string") return detail.message;
    if (typeof detail.error === "string") return detail.error;
  }
  if (typeof record.error === "string") return record.error;
  if (typeof record.message === "string") return record.message;
  return null;
}

function buildQuery(params: Record<string, string | number | undefined | null>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    query.set(key, String(value));
  }
  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}

export async function fetchParcelByClick(lng: number, lat: number, county: string) {
  const url = `/api/parcels/by-click${buildQuery({ lng, lat, county })}`;
  return parseResponse<ParcelLookupResponse>(await fetch(url));
}

export async function fetchParcelsInBounds(
  county: string,
  bounds: { minLng: number; minLat: number; maxLng: number; maxLat: number },
  limit = 2000,
  zoom?: number
) {
  const url = `/api/parcels/in-bounds${buildQuery({
    county,
    minLng: bounds.minLng,
    minLat: bounds.minLat,
    maxLng: bounds.maxLng,
    maxLat: bounds.maxLat,
    limit,
    zoom,
  })}`;
  if (PARCEL_DEBUG_ENABLED) {
    console.log("[parcel-bbox] request", { county, bounds, limit, zoom });
  }
  try {
    const parcels = await parseResponse<DiscoveryParcelRecord[]>(await fetch(url));
    if (PARCEL_DEBUG_ENABLED) {
      console.log("[parcel-bbox] response", {
        county,
        count: parcels.length,
        geometryType: parcels[0]?.geometryGeoJSON?.type ?? null,
      });
    }
    return parcels;
  } catch (error) {
    if (PARCEL_DEBUG_ENABLED) {
      console.error("[parcel-bbox] failed", { county, bounds, limit, error });
    }
    throw error;
  }
}

export async function searchParcelByApn(county: string, apn: string) {
  const url = `/api/parcels/search${buildQuery({ county, apn })}`;
  return parseResponse<DiscoveryParcelRecord[]>(await fetch(url));
}

export async function fetchDiscoveryParcel(parcelId: string) {
  return parseResponse<DiscoveryParcelRecord>(await fetch(`/api/parcels/${parcelId}`));
}

export const fetchParcel = fetchDiscoveryParcel;

export async function fetchRecentParcels(limit = 6) {
  return parseResponse<DiscoveryParcelRecord[]>(await fetch(`/api/parcels/recent?limit=${limit}`));
}

export async function fetchBedrockParcel(parcelId: string) {
  return parseResponse<BedrockParcel>(await fetch(`/api/bedrock/parcel/${parcelId}`));
}

export async function loadBedrockParcel(input: {
  parcel_id?: string;
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  jurisdiction?: string;
}) {
  return parseResponse<BedrockParcel>(
    await fetch(`/api/bedrock/parcel/load`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(input),
    })
  );
}

export async function ensureBedrockParcel(parcelId: string) {
  try {
    return await fetchBedrockParcel(parcelId);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) {
      throw error;
    }
  }

  const discoveryParcel = await fetchDiscoveryParcel(parcelId);
  return loadBedrockParcel(parcelLoadRequestFromDiscovery(discoveryParcel));
}

export async function runBedrockPipeline(parcel: BedrockParcel) {
  return parseResponse<PipelineRun>(
    await fetch(`/api/bedrock/pipeline/run`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ parcel }),
    })
  );
}

export async function fetchRuns(params?: {
  sort?: "ROI" | "projected_profit" | "units" | "timestamp";
  order?: "asc" | "desc";
  min_ROI?: number;
  max_ROI?: number;
  min_units?: number;
  max_units?: number;
  limit?: number;
  offset?: number;
}) {
  const query = buildQuery(params ?? {});
  return parseResponse<PipelineRunSummary[]>(await fetch(`/api/runs${query}`));
}

export async function fetchRecentRuns(limit = 8) {
  return fetchRuns({ limit, sort: "timestamp", order: "desc" });
}

export async function fetchRun(runId: string) {
  return parseResponse<PipelineRun>(await fetch(`/api/runs/${runId}`));
}
