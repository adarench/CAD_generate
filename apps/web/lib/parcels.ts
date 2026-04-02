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
  parcel_id: string;
  units: number;
  estimated_home_price: number;
  price_per_sqft: number;
  estimated_home_size_sqft: number;
  construction_cost_per_sqft: number;
  construction_cost_per_home: number;
  development_cost_total: number;
  projected_revenue: number;
  projected_cost: number;
  projected_profit: number;
  ROI?: number | null;
  ROI_base?: number | null;
  ROI_best_case?: number | null;
  ROI_worst_case?: number | null;
  break_even_price?: number | null;
  profit_margin?: number | null;
  revenue_per_unit?: number | null;
  cost_per_unit?: number | null;
  risk_score?: number | null;
  confidence: number;
  confidence_score?: number | null;
  key_risk_factors?: string[];
  status?: string | null;
  financial_summary?: Record<string, unknown>;
  assumptions?: Record<string, unknown>;
  constraint_violations?: string[];
};

export type NearFeasibleResult = {
  schema_name: "NearFeasibleResult";
  schema_version: string;
  status: "near_feasible";
  reason_category: string;
  limiting_constraints: Record<string, unknown>;
  required_relaxation: Record<string, unknown>;
  best_attempt_summary: Record<string, unknown>;
  financial_upside?: Record<string, unknown>;
  attempted_strategies: string[];
  attempted_repairs: string[];
};

export type PipelineRun = {
  schema_name: "PipelineRun";
  schema_version: string;
  run_id: string;
  status: "completed" | "near_feasible" | "failed";
  parcel_id: string;
  zoning_result: BedrockZoningRules;
  layout_result?: BedrockLayoutResult | null;
  feasibility_result?: BedrockFeasibilityResult | null;
  near_feasible_result?: NearFeasibleResult | null;
  inferred_analysis?: InferredAnalysis | null;
  timestamp: string;
  git_commit?: string | null;
  input_hash?: string | null;
  stage_runtimes?: Record<string, number>;
  zoning_bypassed?: boolean;
  bypass_reason?: string | null;
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

// --- Optimization pipeline types (mirrors bedrock/contracts/optimization_run.py) ---

export type OptimizationObjective = {
  roi_weight?: number;
  profit_weight?: number;
  risk_weight?: number;
  confidence_weight?: number;
  min_roi?: number | null;
  max_risk?: number | null;
  improvement_epsilon?: number;
  target_score?: number;
};

export type SensitivityBreakpoint = {
  variable: string;
  current_value: number | null;
  break_even_value: number | null;
  margin_value: number | null;
  margin_percent: number | null;
  explanation: string;
};

export type CandidateSensitivity = {
  layout_id: string;
  status: "best_candidate" | "near_feasible" | "failing_candidate";
  primary_failure_reason: string;
  margin_to_feasibility: number;
  make_it_work_statement: string;
  breakpoints: SensitivityBreakpoint[];
};

export type EconomicScenario = {
  scenario_name: string;
  scenario_type: "land_price_sweep" | "density_curve" | "rezoning";
  status: "evaluated" | "not_applicable";
  best_layout_id: string | null;
  best_roi: number | null;
  best_projected_profit: number | null;
  delta_roi: number | null;
  delta_profit: number | null;
  recommended_max_offer_price: number | null;
  curve: Array<Record<string, unknown>>;
  explanation: string | null;
};

export type OptimizationDecision = {
  recommendation: "acquire" | "renegotiate_price" | "pursue_rezoning" | "abandon";
  action: "acquire" | "renegotiate_price" | "pursue_rezoning" | "abandon" | null;
  best_layout_id: string | null;
  expected_roi_base: number | null;
  expected_roi_best_case: number | null;
  expected_roi_worst_case: number | null;
  sensitivity: string[];
  key_risks: string[];
  breakpoints: SensitivityBreakpoint[];
  target_price: number | null;
  reason: string | null;
  alternative: string | null;
  rationale: string | null;
};

export type OptimizationCandidate = {
  layout_result: BedrockLayoutResult;
  feasibility_result: BedrockFeasibilityResult;
  strategy_parameters: Record<string, unknown>;
  objective_score: number;
  optimization_rank: number;
};

export type OptimizationIteration = {
  iteration_index: number;
  candidate_count: number;
  best_layout_id: string | null;
  best_objective_score: number | null;
  best_roi: number | null;
  best_projected_profit: number | null;
  improvement_from_prior: number | null;
};

export type ConvergenceMetrics = {
  iteration_count: number;
  plateau_reached: boolean;
  stopped_reason: string | null;
  improvement_curve: number[];
};

export type OptimizationRun = {
  schema_name: "OptimizationRun";
  schema_version: string;
  optimization_run_id: string;
  parcel_id: string;
  zoning_result: BedrockZoningRules;
  layout_candidates: OptimizationCandidate[];
  best_candidate: OptimizationCandidate | null;
  ranking_metrics: Record<string, unknown>;
  objective: OptimizationObjective;
  iterations: OptimizationIteration[];
  convergence_metrics: ConvergenceMetrics | null;
  sensitivity_analysis: CandidateSensitivity[];
  economic_scenarios: EconomicScenario[];
  decision: OptimizationDecision | null;
  selected_pipeline_run_id: string | null;
  timestamp: string;
  git_commit: string | null;
  input_hash: string | null;
  stage_runtimes: Record<string, number>;
};

export type OptimizationRunSummary = {
  optimization_run_id: string;
  timestamp: string;
  parcel_id: string | null;
  candidate_count: number;
  best_layout_id: string | null;
  best_roi: number | null;
  best_projected_profit: number | null;
  selected_pipeline_run_id: string | null;
};

// --- Inferred analysis types ---

export type InferredAnalysis = {
  mode: "INFERRED";
  parcel_id: string;
  jurisdiction: string;
  area_acres: number;
  zoning_assumption: string;
  density_estimate_du_ac: number;
  min_lot_size_sqft_estimate: number;
  estimated_units_low: number;
  estimated_units_high: number;
  estimated_units_mid: number;
  price_per_unit: number;
  cost_per_unit: number;
  projected_revenue: number;
  projected_cost: number;
  projected_profit: number;
  roi: number;
  confidence: number;
  reasoning_summary: string;
  key_assumptions: string[];
  recommendation: "acquire" | "renegotiate_price" | "pursue_rezoning" | "abandon";
};

// --- Batch optimization types ---

export type BatchOptimizeResultItem = {
  parcel_id: string;
  optimization_run_id: string | null;
  recommendation: string | null;
  roi: number | null;
  projected_profit: number | null;
  units: number | null;
  status: string;
  error: string | null;
};

export type BatchOptimizeResponse = {
  results: BatchOptimizeResultItem[];
  total: number;
  succeeded: number;
  failed: number;
};

// --- Decision record types ---

export type DecisionRecord = {
  schema_name: "DecisionRecord";
  schema_version: string;
  decision_id: string;
  parcel_id: string;
  optimization_run_id: string | null;
  pipeline_run_id: string | null;
  system_recommendation: "acquire" | "renegotiate_price" | "pursue_rezoning" | "abandon" | null;
  user_action: "acquire" | "pass" | "hold" | "renegotiate" | "rezoning_in_progress" | null;
  user_action_at: string | null;
  status: "new" | "in_review" | "decided" | "in_progress" | "closed" | "abandoned";
  target_price: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

// --- Legacy aliases ---

export type ParcelRecord = DiscoveryParcelRecord;
export type RunSummary = PipelineRunSummary;
export type RunDetail = PipelineRun;
export type OptimizationResponse = LayoutVisualizationResult;
export type PipelineRunUiState = "buildable" | "near_feasible" | "failed";

export function parcelLoadRequestFromDiscovery(parcel: DiscoveryParcelRecord) {
  return {
    parcel_id: parcel.id,
    geometry: parcel.geometryGeoJSON,
    jurisdiction: inferJurisdictionFromDiscovery(parcel),
    zoning_district: parcel.zoningCode,
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
): LayoutVisualizationResult | null {
  if (!run.layout_result) {
    return null;
  }
  return layoutVisualizationFromLayoutResult(run.layout_result, parcel, run.run_id, run.zoning_result);
}

export function layoutVisualizationFromLayoutResult(
  layout: BedrockLayoutResult,
  parcel?: BedrockParcel | null,
  runId = "design-mode",
  zoning?: BedrockZoningRules | null
): LayoutVisualizationResult {
  const parcelAreaSqft = parcel?.area_sqft ?? null;
  const lotCount = layout.unit_count;
  const averageLotAreaSqft =
    parcelAreaSqft && lotCount > 0 ? Math.round(parcelAreaSqft / lotCount) : null;

  return {
    runId,
    layoutId: layout.layout_id,
    lotCount,
    roadLengthFt: layout.road_length_ft,
    parcelAreaSqft,
    averageLotAreaSqft,
    resultGeoJSON: layoutResultToFeatureCollection(layout, parcel, zoning),
  };
}

export function pipelineRunUiState(run: PipelineRun | null | undefined): PipelineRunUiState | null {
  if (!run) return null;
  if (run.status === "completed") return "buildable";
  if (run.status === "near_feasible") return "near_feasible";
  return "failed";
}

export function pipelineRunStateLabel(run: PipelineRun | null | undefined): string {
  const state = pipelineRunUiState(run);
  if (state === "buildable") return "Buildable";
  if (state === "near_feasible") return "Near-feasible";
  if (state === "failed") return "Failed";
  return "Not run";
}

export function pipelineRunExplanation(run: PipelineRun | null | undefined): string | null {
  if (!run) return null;
  if (run.status === "completed") {
    return "The parcel produced a complete layout and feasibility result.";
  }
  if (run.status === "near_feasible") {
    const reason = run.near_feasible_result?.reason_category
      ? run.near_feasible_result.reason_category.replace(/_/g, " ")
      : run.bypass_reason
        ? run.bypass_reason.replace(/_/g, " ")
        : "layout or zoning constraints";
    return `${run.zoning_result.district} is close to feasible but currently blocked by ${reason}.`;
  }
  return `${run.zoning_result.district} failed to produce a completed or near-feasible outcome.`;
}

export function layoutResultToFeatureCollection(
  layout: BedrockLayoutResult,
  parcel?: BedrockParcel | null,
  zoning?: BedrockZoningRules | null
): GeoJSON.FeatureCollection {
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

  const roadGeometries = parcel ? roadFootprintGeometries(layout.road_geometries, parcel, zoning) : layout.road_geometries;
  for (const [index, geometry] of roadGeometries.entries()) {
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

const FEET_PER_DEGREE_LAT = 364000;
const DEFAULT_ROAD_WIDTH_FT = 32;

function roadFootprintGeometries(
  geometries: BedrockLayoutGeometry[],
  parcel: BedrockParcel,
  zoning?: BedrockZoningRules | null
): BedrockLayoutGeometry[] {
  const roadWidthFt = zoning?.road_right_of_way_ft ?? DEFAULT_ROAD_WIDTH_FT;
  const projection = projectionFromParcel(parcel);
  const polygons: GeoJSON.Polygon[] = [];

  for (const geometry of geometries) {
    if (geometry.type === "Polygon" || geometry.type === "MultiPolygon") {
      polygons.push(...flattenPolygonGeometry(geometry));
      continue;
    }
    if (geometry.type === "LineString") {
      polygons.push(...bufferLineStringGeometry(geometry.coordinates, projection, roadWidthFt));
      continue;
    }
    for (const line of geometry.coordinates) {
      polygons.push(...bufferLineStringGeometry(line, projection, roadWidthFt));
    }
  }

  return polygons;
}

function projectionFromParcel(parcel: BedrockParcel) {
  const [lng, lat] = parcel.centroid ?? centroidFromGeometry(parcel.geometry);
  const feetPerDegreeLng = FEET_PER_DEGREE_LAT * Math.cos((lat * Math.PI) / 180);
  return {
    originLng: lng,
    originLat: lat,
    feetPerDegreeLng: Math.max(feetPerDegreeLng, 1),
    feetPerDegreeLat: FEET_PER_DEGREE_LAT,
  };
}

function bufferLineStringGeometry(
  points: number[][],
  projection: {
    originLng: number;
    originLat: number;
    feetPerDegreeLng: number;
    feetPerDegreeLat: number;
  },
  roadWidthFt: number
): GeoJSON.Polygon[] {
  if (points.length < 2 || roadWidthFt <= 0) return [];
  const polygons: GeoJSON.Polygon[] = [];
  const halfWidthFt = roadWidthFt / 2;

  for (let index = 0; index < points.length - 1; index += 1) {
    const start = toLocalPoint(points[index], projection);
    const end = toLocalPoint(points[index + 1], projection);
    const dx = end[0] - start[0];
    const dy = end[1] - start[1];
    const length = Math.hypot(dx, dy);
    if (length <= 0) continue;
    const offsetX = (-dy / length) * halfWidthFt;
    const offsetY = (dx / length) * halfWidthFt;
    const ring = [
      toLngLatPoint([start[0] + offsetX, start[1] + offsetY], projection),
      toLngLatPoint([end[0] + offsetX, end[1] + offsetY], projection),
      toLngLatPoint([end[0] - offsetX, end[1] - offsetY], projection),
      toLngLatPoint([start[0] - offsetX, start[1] - offsetY], projection),
      toLngLatPoint([start[0] + offsetX, start[1] + offsetY], projection),
    ];
    polygons.push({
      type: "Polygon",
      coordinates: [ring],
    });
  }

  return polygons;
}

function flattenPolygonGeometry(geometry: Extract<BedrockLayoutGeometry, GeoJSON.Polygon | GeoJSON.MultiPolygon>): GeoJSON.Polygon[] {
  if (geometry.type === "Polygon") return [geometry];
  return geometry.coordinates.map((polygon) => ({
    type: "Polygon",
    coordinates: polygon,
  }));
}

function toLocalPoint(
  point: number[],
  projection: {
    originLng: number;
    originLat: number;
    feetPerDegreeLng: number;
    feetPerDegreeLat: number;
  }
): [number, number] {
  return [
    (point[0] - projection.originLng) * projection.feetPerDegreeLng,
    (point[1] - projection.originLat) * projection.feetPerDegreeLat,
  ];
}

function toLngLatPoint(
  point: [number, number],
  projection: {
    originLng: number;
    originLat: number;
    feetPerDegreeLng: number;
    feetPerDegreeLat: number;
  }
): [number, number] {
  return [
    projection.originLng + point[0] / projection.feetPerDegreeLng,
    projection.originLat + point[1] / projection.feetPerDegreeLat,
  ];
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
