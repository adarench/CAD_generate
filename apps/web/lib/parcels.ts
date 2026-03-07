export type ParcelRecord = {
  id: string;
  state: "UT";
  county: string;
  apn: string | null;
  sourceProvider: string;
  sourceDataset: string;
  sourceObjectId: string | null;
  geometryGeoJSON: GeoJSON.Polygon | GeoJSON.MultiPolygon;
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

export type RunSummary = {
  runId: string;
  parcelId: string;
  parcelApn: string | null;
  county: string | null;
  winningTopology: string;
  lotCount: number;
  createdAt: string;
  status: "completed" | "failed";
};

export type CandidateSummary = {
  topology: string;
  candidatesTested: number;
  lots: number;
  roadLength: number;
  developableAreaSqft: number;
  status: string;
  notes?: string | null;
};

export type OptimizationResponse = {
  runId: string;
  winningTopology: string;
  lotCount: number;
  parcelAreaSqft: number;
  roadLengthFt: number;
  developableAreaSqft: number;
  averageLotAreaSqft: number;
  candidateSummary: CandidateSummary[];
  resultGeoJSON: GeoJSON.FeatureCollection;
  exports: Record<string, string>;
};

export type ParcelLookupResponse = {
  selected: ParcelRecord | null;
  candidates: ParcelRecord[];
  message?: string | null;
};

export type RunDetail = {
  runId: string;
  parcelId: string;
  status: "completed" | "failed";
  parcel: ParcelRecord | null;
  inputConstraints: Record<string, unknown>;
  topologyPreferences: string[];
  strictTopology: boolean;
  createdAt: string;
  response: OptimizationResponse;
};
