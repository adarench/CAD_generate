import type {
  InferredAnalysis,
  BatchOptimizeResponse,
  BedrockLayoutResult,
  BedrockParcel,
  BedrockZoningRules,
  DecisionRecord,
  DiscoveryParcelRecord,
  OptimizationObjective,
  OptimizationRun,
  OptimizationRunSummary,
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
  const formatDetail = (detail: Record<string, unknown>) => {
    const pieces: string[] = [];
    if (typeof detail.reason_category === "string") {
      pieces.push(detail.reason_category.replace(/_/g, " "));
    }
    if (typeof detail.message === "string") {
      pieces.push(detail.message);
    } else if (typeof detail.error === "string") {
      pieces.push(detail.error);
    }
    const constraints: string[] = [];
    if (typeof detail.min_lot_area_sqft === "number") {
      constraints.push(`min lot ${Math.round(detail.min_lot_area_sqft).toLocaleString()} sqft`);
    }
    if (typeof detail.required_frontage_ft === "number") {
      constraints.push(`required frontage ${detail.required_frontage_ft.toFixed(1)} ft`);
    }
    if (typeof detail.approx_frontage_ft === "number") {
      constraints.push(`available frontage ${detail.approx_frontage_ft.toFixed(1)} ft`);
    }
    if (constraints.length) {
      pieces.push(constraints.join(" | "));
    }
    return pieces.filter(Boolean).join(" — ");
  };
  if (typeof record.detail === "string") return record.detail;
  if (record.detail && typeof record.detail === "object") {
    const detail = record.detail as Record<string, unknown>;
    const formatted = formatDetail(detail);
    if (formatted) return formatted;
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

export async function fetchParcelByClick(
  lng: number,
  lat: number,
  county: string,
  options?: { signal?: AbortSignal }
) {
  const url = `/api/parcels/by-click${buildQuery({ lng, lat, county })}`;
  return parseResponse<ParcelLookupResponse>(await fetch(url, { signal: options?.signal }));
}

export async function fetchParcelsInBounds(
  county: string,
  bounds: { minLng: number; minLat: number; maxLng: number; maxLat: number },
  limit = 2000,
  zoom?: number,
  options?: { signal?: AbortSignal }
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
    const parcels = await parseResponse<DiscoveryParcelRecord[]>(
      await fetch(url, { signal: options?.signal })
    );
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

export async function searchParcelByApn(
  county: string,
  apn: string,
  options?: { signal?: AbortSignal }
) {
  const url = `/api/parcels/search${buildQuery({ county, apn })}`;
  return parseResponse<DiscoveryParcelRecord[]>(await fetch(url, { signal: options?.signal }));
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
  zoning_district?: string | null;
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

export async function runBedrockLayoutSearch(input: {
  parcel: BedrockParcel;
  zoning: BedrockZoningRules;
  max_candidates?: number;
}) {
  return parseResponse<BedrockLayoutResult>(
    await fetch(`/api/bedrock/layout/search`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        parcel: input.parcel,
        zoning: input.zoning,
        max_candidates: input.max_candidates ?? 50,
      }),
    })
  );
}

export async function exportBedrockLayout(input: {
  parcel: BedrockParcel;
  layout: BedrockLayoutResult;
  zoning?: BedrockZoningRules | null;
  format?: "dxf" | "step" | "geojson";
}) {
  const response = await fetch(`/api/bedrock/layout/export`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      parcel: input.parcel,
      layout: input.layout,
      zoning: input.zoning ?? undefined,
      format: input.format ?? "dxf",
    }),
  });
  if (!response.ok) {
    let payload: unknown = null;
    let detail = "Export failed.";
    try {
      payload = await response.json();
      detail = extractErrorMessage(payload) ?? detail;
    } catch {
      try {
        detail = await response.text();
      } catch {
        detail = "Export failed.";
      }
    }
    throw new ApiError(detail, response.status, payload);
  }

  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const filenameMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
  const filename = filenameMatch?.[1] ?? `layout-export.${input.format ?? "dxf"}`;
  return { blob, filename };
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

// --- Inferred analysis ---

export async function runInferredAnalysis(parcelId: string) {
  return parseResponse<InferredAnalysis>(
    await fetch(`/api/bedrock/pipeline/infer`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ parcel_id: parcelId }),
    })
  );
}

// --- Optimization pipeline ---

export async function runBedrockOptimize(
  parcel: BedrockParcel,
  objective?: Partial<OptimizationObjective>,
  maxRounds?: number,
) {
  return parseResponse<OptimizationRun>(
    await fetch(`/api/bedrock/pipeline/optimize`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        parcel,
        objective: objective ?? undefined,
        max_rounds: maxRounds ?? 3,
      }),
    })
  );
}

export async function runBedrockOptimizeBatch(parcelIds: string[]) {
  return parseResponse<BatchOptimizeResponse>(
    await fetch(`/api/bedrock/pipeline/optimize-batch`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ parcel_ids: parcelIds }),
    })
  );
}

export async function fetchOptimizationRuns(params?: {
  limit?: number;
  offset?: number;
}) {
  const query = buildQuery(params ?? {});
  return parseResponse<OptimizationRunSummary[]>(
    await fetch(`/api/optimization/runs${query}`)
  );
}

export async function fetchOptimizationRun(optimizationRunId: string) {
  return parseResponse<OptimizationRun>(
    await fetch(`/api/optimization/runs/${optimizationRunId}`)
  );
}

// --- Decision persistence ---

export async function createDecision(input: {
  parcel_id: string;
  optimization_run_id?: string | null;
  pipeline_run_id?: string | null;
  system_recommendation?: string | null;
  user_action?: string | null;
  target_price?: number | null;
  notes?: string | null;
}) {
  return parseResponse<DecisionRecord>(
    await fetch(`/api/decisions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(input),
    })
  );
}

export async function fetchDecisions(params?: {
  parcel_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}) {
  const query = buildQuery(params ?? {});
  return parseResponse<DecisionRecord[]>(await fetch(`/api/decisions${query}`));
}

export async function fetchDecision(decisionId: string) {
  return parseResponse<DecisionRecord>(await fetch(`/api/decisions/${decisionId}`));
}

export async function updateDecision(
  decisionId: string,
  fields: {
    user_action?: string | null;
    status?: string | null;
    target_price?: number | null;
    notes?: string | null;
  },
) {
  return parseResponse<DecisionRecord>(
    await fetch(`/api/decisions/${decisionId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(fields),
    })
  );
}
