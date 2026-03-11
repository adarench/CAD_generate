import { OptimizationResponse, ParcelRecord } from "./parcels";

export type PlannerConstraints = {
  minFrontage: number;
  minDepth: number;
  minArea: number;
  roadWidth: number;
  easementWidth: number;
  lotCount: number;
  roadOrientation: "north_south" | "east_west";
};

export type PlannerConstraintOverrides = Partial<PlannerConstraints>;

export async function runOptimizationApi(
  parcel: ParcelRecord,
  constraints: PlannerConstraintOverrides,
  topologyPreferences: string[],
  strictTopology: boolean,
  conceptText?: string
) {
  const response = await fetch("/api/optimization", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      parcelId: parcel.id,
      designConstraints: constraints,
      topologyPreferences,
      strictTopology,
      conceptText,
    }),
  });
  if (!response.ok) {
    let detail = "Optimization service error";
    try {
      const payload = await response.json();
      detail = payload.detail ?? payload.error ?? detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  return (await response.json()) as OptimizationResponse;
}
