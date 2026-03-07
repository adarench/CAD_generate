CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS parcels (
  id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  county TEXT NOT NULL,
  apn TEXT,
  source_provider TEXT,
  source_dataset TEXT,
  source_object_id TEXT,
  geometry geometry(MultiPolygon, 4326),
  centroid geometry(Point, 4326),
  area_sqft DOUBLE PRECISION,
  area_acres DOUBLE PRECISION,
  address TEXT,
  owner_name TEXT,
  zoning_code TEXT,
  land_use TEXT,
  raw_attributes JSONB,
  fetched_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parcels_county_apn ON parcels(county, apn);
CREATE INDEX IF NOT EXISTS idx_parcels_geom ON parcels USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_parcels_updated_at ON parcels(updated_at DESC);

CREATE TABLE IF NOT EXISTS optimization_runs (
  id TEXT PRIMARY KEY,
  parcel_id TEXT REFERENCES parcels(id),
  input_constraints JSONB,
  preferred_topologies JSONB,
  strict_topology BOOLEAN,
  run_status TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS optimization_results (
  id TEXT PRIMARY KEY,
  run_id TEXT REFERENCES optimization_runs(id),
  winning_topology TEXT,
  candidate_summary_json JSONB,
  max_lot_count INTEGER,
  developable_area_sqft DOUBLE PRECISION,
  road_length_ft DOUBLE PRECISION,
  avg_lot_area_sqft DOUBLE PRECISION,
  result_geojson JSONB,
  exports_json JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS parcel_sources (
  id TEXT PRIMARY KEY,
  provider TEXT,
  dataset_name TEXT,
  dataset_url TEXT,
  refresh_status TEXT,
  metadata_json JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
