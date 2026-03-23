export type DiscoveryParcelRecord = {
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

export type ParcelLookupResponse = {
  selected: DiscoveryParcelRecord | null;
  candidates: DiscoveryParcelRecord[];
  message?: string | null;
};

export type BedrockParcel = {
  schema_name: "Parcel";
  schema_version: string;
  parcel_id: string;
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  jurisdiction: string;
  area_sqft: number;
  centroid: [number, number] | null;
  bounding_box?: [number, number, number, number] | null;
  land_use?: string | null;
  slope_percent?: number | null;
  flood_zone?: string | null;
  zoning_district?: string | null;
  utilities: string[];
  access_points: GeoJSON.Geometry[];
  topography: Record<string, unknown>;
  existing_structures: Record<string, unknown>[];
  metadata?: Record<string, unknown> | null;
};

export type BedrockZoningRules = {
  schema_name: "ZoningRules";
  schema_version: string;
  parcel_id: string;
  jurisdiction?: string | null;
  district: string;
  district_id?: string | null;
  overlays: string[];
  setbacks: {
    front?: number | null;
    side?: number | null;
    rear?: number | null;
  };
  min_lot_size_sqft?: number | null;
  max_units_per_acre?: number | null;
  height_limit_ft?: number | null;
  lot_coverage_max?: number | null;
  min_frontage_ft?: number | null;
  road_right_of_way_ft?: number | null;
  standards?: Array<Record<string, unknown>>;
  citations?: string[];
};

export type BedrockLayoutGeometry =
  | GeoJSON.Polygon
  | GeoJSON.MultiPolygon
  | GeoJSON.LineString
  | GeoJSON.MultiLineString;

export type BedrockLayoutResult = {
  schema_name: "LayoutResult";
  schema_version: string;
  layout_id: string;
  parcel_id: string;
  unit_count: number;
  road_length_ft: number;
  lot_geometries: BedrockLayoutGeometry[];
  road_geometries: BedrockLayoutGeometry[];
  open_space_area_sqft?: number | null;
  utility_length_ft?: number | null;
  score?: number | null;
  buildable_area_sqft?: number | null;
  metadata?: Record<string, unknown> | null;
};

export type BedrockFeasibilityResult = {
  schema_name: "FeasibilityResult";
  schema_version: string;
  scenario_id: string;
  layout_id: string;
  parcel_id?: string | null;
  units: number;
  estimated_home_price: number;
  construction_cost_per_home: number;
  development_cost_total: number;
  projected_revenue: number;
  projected_cost: number;
  projected_profit: number;
  ROI?: number | null;
  profit_margin?: number | null;
  revenue_per_unit?: number | null;
  cost_per_unit?: number | null;
  risk_score?: number | null;
  confidence?: number | null;
  status?: string | null;
  financial_summary?: Record<string, unknown>;
  assumptions?: Record<string, unknown>;
  constraint_violations?: string[];
};

export type PipelineRun = {
  schema_name: "PipelineRun";
  schema_version: string;
  run_id: string;
  parcel_id: string;
  zoning_result: BedrockZoningRules;
  layout_result: BedrockLayoutResult;
  feasibility_result: BedrockFeasibilityResult;
  timestamp: string;
  git_commit?: string | null;
  input_hash?: string | null;
  stage_runtimes?: Record<string, number>;
};

export type PipelineRunSummary = {
  run_id: string;
  timestamp: string;
  parcel_id: string | null;
  units: number | null;
  projected_profit: number | null;
  ROI: number | null;
};

export type ExperimentRun = {
  schema_name: "ExperimentRun";
  schema_version: string;
  experiment_id: string;
  run_ids: string[];
  config: Record<string, unknown>;
  metrics: Record<string, unknown>;
  timestamp: string;
};

export type StudioParcelRecord = {
  id: string;
  county: string;
  apn: string | null;
  geometryGeoJSON: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  centroid: { lng: number; lat: number };
  areaSqft: number | null;
  areaAcres: number | null;
  zoningCode: string | null;
};

export type LayoutVisualizationResult = {
  runId: string;
  layoutId: string;
  lotCount: number;
  roadLengthFt: number;
  parcelAreaSqft: number | null;
  averageLotAreaSqft: number | null;
  resultGeoJSON: GeoJSON.FeatureCollection;
};

export type ConceptInstruction = {
  topologyPreferences?: string[];
  excludedTopologies?: string[];
  densityIntent?: string | null;
  roadIntent?: string | null;
  lotIntent?: string | null;
  edgeConditions?: string[];
  notes?: string | null;
};

export type ParcelRecord = DiscoveryParcelRecord;
export type RunSummary = PipelineRunSummary;
export type RunDetail = PipelineRun;
export type OptimizationResponse = LayoutVisualizationResult;

export function parcelLoadRequestFromDiscovery(parcel: DiscoveryParcelRecord) {
  return {
    parcel_id: parcel.id,
    geometry: parcel.geometryGeoJSON,
    jurisdiction: inferJurisdictionFromDiscovery(parcel),
  };
}

export function studioParcelFromBedrock(parcel: BedrockParcel): StudioParcelRecord {
  const [lng, lat] = parcel.centroid ?? centroidFromGeometry(parcel.geometry);
  return {
    id: parcel.parcel_id,
    county: parcel.jurisdiction,
    apn: extractParcelApn(parcel),
    geometryGeoJSON: parcel.geometry,
    centroid: { lng, lat },
    areaSqft: parcel.area_sqft,
    areaAcres: parcel.area_sqft ? parcel.area_sqft / 43560 : null,
    zoningCode: parcel.zoning_district ?? null,
  };
}

export function layoutVisualizationFromPipelineRun(
  run: PipelineRun,
  parcel?: BedrockParcel | null
): LayoutVisualizationResult {
  const parcelAreaSqft = parcel?.area_sqft ?? null;
  const lotCount = run.layout_result.unit_count;
  const averageLotAreaSqft =
    parcelAreaSqft && lotCount > 0 ? Math.round(parcelAreaSqft / lotCount) : null;

  return {
    runId: run.run_id,
    layoutId: run.layout_result.layout_id,
    lotCount,
    roadLengthFt: run.layout_result.road_length_ft,
    parcelAreaSqft,
    averageLotAreaSqft,
    resultGeoJSON: layoutResultToFeatureCollection(run.layout_result),
  };
}

export function layoutResultToFeatureCollection(layout: BedrockLayoutResult): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];

  for (const [index, geometry] of layout.lot_geometries.entries()) {
    features.push({
      type: "Feature",
      geometry,
      properties: {
        id: `lot-${index + 1}`,
        layer: "lots",
      },
    });

    const centroid = geometryCentroid(geometry);
    if (centroid) {
      features.push({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: centroid,
        },
        properties: {
          id: `lot-label-${index + 1}`,
          layer: "lot_labels",
          text: String(index + 1),
        },
      });
    }
  }

  for (const [index, geometry] of layout.road_geometries.entries()) {
    features.push({
      type: "Feature",
      geometry,
      properties: {
        id: `road-${index + 1}`,
        layer: "road",
      },
    });
  }

  return {
    type: "FeatureCollection",
    features,
  };
}

function extractParcelApn(parcel: BedrockParcel): string | null {
  const metadata = parcel.metadata ?? {};
  const apn = metadata.apn ?? metadata.parcel_apn ?? metadata.apn_number;
  return typeof apn === "string" && apn.trim() ? apn : parcel.parcel_id;
}

function normalizeJurisdiction(county: string): string {
  return county.endsWith(" County") ? county.replace(/\s+County$/i, "") : county;
}

function inferJurisdictionFromDiscovery(parcel: DiscoveryParcelRecord): string {
  const raw = parcel.rawAttributes ?? {};
  const candidates = [
    raw.PARCEL_CITY,
    raw.CITY,
    raw.MUNICIPALITY,
    raw.JURISDICTION,
    raw.SITUS_CITY,
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }
  return normalizeJurisdiction(parcel.county);
}

function centroidFromGeometry(geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon): [number, number] {
  const points = geometry.type === "Polygon" ? geometry.coordinates.flat() : geometry.coordinates.flat(2);
  const total = points.reduce(
    (acc, point) => {
      acc.lng += point[0];
      acc.lat += point[1];
      acc.count += 1;
      return acc;
    },
    { lng: 0, lat: 0, count: 0 }
  );
  if (!total.count) return [0, 0];
  return [total.lng / total.count, total.lat / total.count];
}

function geometryCentroid(geometry: BedrockLayoutGeometry): [number, number] | null {
  if (geometry.type === "Polygon") {
    return ringCentroid(geometry.coordinates[0] ?? []);
  }
  if (geometry.type === "MultiPolygon") {
    const firstPolygon = geometry.coordinates[0];
    return ringCentroid(firstPolygon?.[0] ?? []);
  }
  if (geometry.type === "LineString") {
    return lineCentroid(geometry.coordinates);
  }
  const firstLine = geometry.coordinates[0] ?? [];
  return lineCentroid(firstLine);
}

function ringCentroid(points: number[][]): [number, number] | null {
  if (!points.length) return null;
  const total = points.reduce(
    (acc, point) => {
      acc.lng += point[0];
      acc.lat += point[1];
      acc.count += 1;
      return acc;
    },
    { lng: 0, lat: 0, count: 0 }
  );
  if (!total.count) return null;
  return [total.lng / total.count, total.lat / total.count];
}

function lineCentroid(points: number[][]): [number, number] | null {
  if (!points.length) return null;
  const total = points.reduce(
    (acc, point) => {
      acc.lng += point[0];
      acc.lat += point[1];
      acc.count += 1;
      return acc;
    },
    { lng: 0, lat: 0, count: 0 }
  );
  if (!total.count) return null;
  return [total.lng / total.count, total.lat / total.count];
}
