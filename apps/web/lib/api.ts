import type { ParcelLookupResponse, ParcelRecord, RunDetail, RunSummary } from "@/lib/parcels";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = "Request failed.";
    try {
      const payload = await response.json();
      detail = payload.detail ?? payload.error ?? detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function fetchParcelByClick(lng: number, lat: number, county: string) {
  const url = new URL("/api/parcels/by-click", window.location.origin);
  url.searchParams.set("lng", String(lng));
  url.searchParams.set("lat", String(lat));
  url.searchParams.set("county", county);
  return parseResponse<ParcelLookupResponse>(await fetch(url.toString()));
}

export async function searchParcelByApn(county: string, apn: string) {
  const url = new URL("/api/parcels/search", window.location.origin);
  url.searchParams.set("county", county);
  url.searchParams.set("apn", apn);
  return parseResponse<ParcelRecord[]>(await fetch(url.toString()));
}

export async function fetchParcel(parcelId: string) {
  return parseResponse<ParcelRecord>(await fetch(`/api/parcels/${parcelId}`));
}

export async function fetchRecentParcels(limit = 6) {
  return parseResponse<ParcelRecord[]>(await fetch(`/api/parcels/recent?limit=${limit}`));
}

export async function fetchRun(runId: string) {
  return parseResponse<RunDetail>(await fetch(`/api/runs/${runId}`));
}

export async function fetchRecentRuns(limit = 8) {
  return parseResponse<RunSummary[]>(await fetch(`/api/runs?limit=${limit}`));
}
